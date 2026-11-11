"""Users, roles, authentication (scrypt + signed expiring tokens) and contexts."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from pypos.core.context import OperationContext
from pypos.core.entity import Entity
from pypos.core.service import Service
from pypos.core.store import CollectionSpec, Transaction
from pypos.exceptions import (
    AuthenticationError,
    ConfigurationError,
    DuplicateError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from pypos.users.permissions import BUILTIN_ROLES, PERMISSIONS, is_valid_permission

__all__ = ["BUILTIN_ROLES", "PERMISSIONS", "Role", "User", "UserService", "hash_password"]

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


@dataclass(kw_only=True)
class User(Entity):
    username: str = ""
    display_name: str = ""
    password_hash: str = ""
    roles: list[str] = field(default_factory=list)
    branch_ids: list[str] = field(default_factory=list)  # empty = all branches
    active: bool = True
    failed_logins: int = 0
    locked: bool = False


@dataclass(kw_only=True)
class Role(Entity):
    name: str = ""
    permissions: list[str] = field(default_factory=list)
    builtin: bool = False


USERS = CollectionSpec("users", User, unique=(("merchant_id", "username"),))
ROLES = CollectionSpec("roles", Role, unique=(("merchant_id", "name"),))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    b64 = base64.b64encode
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${b64(salt).decode()}${b64(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt_b64),
            n=int(n), r=int(r), p=int(p), dklen=32,
        )  # fmt: skip
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except (ValueError, TypeError):
        return False


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class UserService(Service):
    #roles
    def ensure_builtin_roles(self, tx: Transaction, merchant_id: str) -> None:
        coll = tx.of(ROLES)
        for name, perms in BUILTIN_ROLES.items():
            if coll.first(merchant_id=merchant_id, name=name) is None:
                coll.add(
                    Role(
                        merchant_id=merchant_id, name=name, permissions=sorted(perms), builtin=True
                    )
                )

    def create_role(self, ctx: OperationContext, name: str, permissions: list[str]) -> Role:
        ctx.require("users.manage")
        bad = [p for p in permissions if not is_valid_permission(p)]
        if bad or not name.strip():
            raise ValidationError("invalid role definition", invalid_permissions=bad)
        with self.tx() as tx:
            self.ensure_builtin_roles(tx, ctx.merchant_id)
            try:
                role = tx.of(ROLES).add(
                    Role(
                        merchant_id=ctx.merchant_id,
                        name=name.strip(),
                        permissions=sorted(set(permissions)),
                    )
                )
            except DuplicateError as exc:
                raise DuplicateError(f"role {name!r} already exists") from exc
            self.audit(tx, ctx, "role.created", "role", role.id, name=role.name)
            return role

    #users
    def _check_password(self, password: str) -> None:
        if len(password) < self.config.password_min_length:
            raise ValidationError(
                f"password must have at least {self.config.password_min_length} characters"
            )

    def create_user(
        self,
        ctx: OperationContext,
        username: str,
        password: str,
        *,
        display_name: str = "",
        roles: list[str] | None = None,
        branch_ids: list[str] | None = None,
    ) -> User:
        ctx.require("users.manage")
        username = username.strip().lower()
        if not username:
            raise ValidationError("username is required")
        self._check_password(password)
        roles = roles or ["cashier"]
        with self.tx() as tx:
            self.ensure_builtin_roles(tx, ctx.merchant_id)
            known = {r.name for r in tx.of(ROLES).find(merchant_id=ctx.merchant_id)}
            if set(roles) - known:
                raise ValidationError("unknown roles", unknown=sorted(set(roles) - known))
            try:
                user = tx.of(USERS).add(
                    User(
                        merchant_id=ctx.merchant_id,
                        username=username,
                        display_name=display_name or username,
                        password_hash=hash_password(password),
                        roles=roles,
                        branch_ids=branch_ids or [],
                    )
                )
            except DuplicateError as exc:
                raise DuplicateError(f"username {username!r} already exists") from exc
            self.audit(tx, ctx, "user.created", "user", user.id, username=username, roles=roles)
            return user

    def create_admin(self, username: str, password: str, merchant_id: str | None = None) -> User:
        """Bootstrap the first administrator (used by the CLI)."""
        return self.create_user(
            OperationContext.system(merchant_id or self.config.merchant_id),
            username,
            password,
            roles=["admin"],
        )

    def set_active(self, ctx: OperationContext, user_id: str, active: bool) -> User:
        ctx.require("users.manage")
        with self.tx() as tx:
            user = self.load(tx.of(USERS), user_id, ctx)
            user.active = active
            if active:
                user.locked, user.failed_logins = False, 0
            tx.of(USERS).save(user)
            self.audit(tx, ctx, "user.active_changed", "user", user.id, active=active)
            return user

    def change_password(self, ctx: OperationContext, user_id: str, new_password: str) -> None:
        if user_id != ctx.user_id:
            ctx.require("users.manage")
        self._check_password(new_password)
        with self.tx() as tx:
            user = self.load(tx.of(USERS), user_id, ctx)
            user.password_hash = hash_password(new_password)
            tx.of(USERS).save(user)
            self.audit(tx, ctx, "user.password_changed", "user", user.id)

    def list_users(self, ctx: OperationContext) -> list[User]:
        ctx.require("users.read")
        with self.tx() as tx:
            return tx.of(USERS).find(merchant_id=ctx.merchant_id)

    # ---- authentication ----------------------------------------------
    def authenticate(self, username: str, password: str, merchant_id: str | None = None) -> User:
        merchant = merchant_id or self.config.merchant_id
        failure: str | None = None
        user: User | None = None
        with self.tx() as tx:  # failures must persist, so raise only after commit
            coll = tx.of(USERS)
            user = coll.first(merchant_id=merchant, username=username.strip().lower())
            if user is None:
                hash_password("dummy-password-for-timing")  # equalise timing
                failure = "invalid credentials"
            elif not user.active or user.locked:
                failure = "account disabled or locked"
            elif not verify_password(password, user.password_hash):
                user.failed_logins += 1
                if user.failed_logins >= self.config.max_failed_logins:
                    user.locked = True
                coll.save(user)
                failure = "invalid credentials"
            else:
                if user.failed_logins:
                    user.failed_logins = 0
                    coll.save(user)
        if failure or user is None:
            raise AuthenticationError(failure or "invalid credentials")
        return user

    def effective_permissions(self, tx: Transaction, user: User) -> frozenset[str]:
        perms: set[str] = set()
        roles = {r.name: r for r in tx.of(ROLES).find(merchant_id=user.merchant_id)}
        for name in user.roles:
            if name in roles:
                perms.update(roles[name].permissions)
        return frozenset(perms)

    def context_for(
        self, user_id: str, *, merchant_id: str | None = None,
        branch_id: str | None = None, terminal_id: str | None = None,
    ) -> OperationContext:  # fmt: skip
        merchant = merchant_id or self.config.merchant_id
        with self.tx() as tx:
            user = tx.of(USERS).get(user_id)
            if user is None or user.merchant_id != merchant or not user.active or user.locked:
                raise AuthenticationError("user is not available")
            if branch_id and user.branch_ids and branch_id not in user.branch_ids:
                raise PermissionDeniedError(
                    "user has no access to this branch", branch_id=branch_id
                )
            perms = self.effective_permissions(tx, user)
        return OperationContext(user.id, user.username, merchant, branch_id, terminal_id, perms)

    # ---- tokens -------------------------------------------------------
    def _secret(self) -> bytes:
        key = self.config.secret_key
        if key is None or len(key.get_secret_value()) < 32:
            raise ConfigurationError("secret_key (>= 32 characters) is required for tokens")
        return key.get_secret_value().encode()

    def issue_token(self, user: User, *, ttl: int | None = None) -> str:
        now = int(time.time())
        payload = {"sub": user.id, "mid": user.merchant_id, "iat": now,
                   "exp": now + (ttl or self.config.token_ttl_seconds)}  # fmt: skip
        body = _b64u(json.dumps(payload, separators=(",", ":")).encode())
        sig = _b64u(hmac.new(self._secret(), body.encode(), hashlib.sha256).digest())
        return f"{body}.{sig}"

    def verify_token(self, token: str) -> dict[str, Any]:
        try:
            body, sig = token.split(".")
            expected = _b64u(hmac.new(self._secret(), body.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(sig, expected):
                raise AuthenticationError("invalid token")
            payload: dict[str, Any] = json.loads(_unb64u(body))
        except (ValueError, TypeError) as exc:
            raise AuthenticationError("invalid token") from exc
        if int(payload.get("exp", 0)) < int(time.time()):
            raise AuthenticationError("token expired")
        return payload

    def login(self, username: str, password: str, merchant_id: str | None = None) -> str:
        return self.issue_token(self.authenticate(username, password, merchant_id))

    def context_from_token(
        self, token: str, *, branch_id: str | None = None, terminal_id: str | None = None
    ) -> OperationContext:
        payload = self.verify_token(token)
        return self.context_for(
            payload["sub"], merchant_id=payload["mid"], branch_id=branch_id, terminal_id=terminal_id
        )

    def get(self, ctx: OperationContext, user_id: str) -> User:
        ctx.require("users.read")
        with self.tx() as tx:
            user = tx.of(USERS).get(user_id)
        if user is None or user.merchant_id != ctx.merchant_id:
            raise NotFoundError("user not found")
        return user
