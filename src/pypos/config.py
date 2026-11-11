"""Framework configuration (validated with Pydantic)."""

from __future__ import annotations

import os
import re
from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from pypos.exceptions import ConfigurationError
from pypos.types import ROUNDING_MODES

_URL_RE = re.compile(r"^(memory://|sqlite(\+\w+)?://|postgresql(\+\w+)?://)")
_CRED_RE = re.compile(r"://([^:/@]+):[^@]*@")


def _mask_url(url: str) -> str:
    return _CRED_RE.sub(r"://\1:********@", url)


class POSConfig(BaseModel):
    """All settings have safe defaults; nothing secret is ever defaulted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    database_url: str = "memory://"
    currency: str = "MXN"
    timezone: str = "UTC"
    merchant_id: str = "default"
    rounding: Literal["HALF_UP", "HALF_EVEN", "DOWN", "UP"] = "HALF_UP"
    allow_negative_stock: bool = False
    auto_create_schema: bool = True
    db_echo: bool = False
    secret_key: SecretStr | None = None
    token_ttl_seconds: int = Field(default=3600, ge=60, le=86400 * 30)
    max_failed_logins: int = Field(default=5, ge=1)
    password_min_length: int = Field(default=10, ge=8)
    return_auth_threshold: Decimal | None = Decimal("500.00")
    receipt_width: int = Field(default=40, ge=24, le=80)
    receipt_header: tuple[str, ...] = ()
    receipt_footer: tuple[str, ...] = ("Thank you!",)
    event_errors_raise: bool = False

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Z]{3}", v):
            raise ValueError("currency must be an ISO 4217 code such as 'MXN'")
        return v

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone {v!r}") from exc
        return v

    @field_validator("database_url")
    @classmethod
    def _db(cls, v: str) -> str:
        if not _URL_RE.match(v):
            raise ValueError("database_url must start with memory://, sqlite:// or postgresql://")
        return v

    @property
    def rounding_mode(self) -> str:
        return ROUNDING_MODES[self.rounding]

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @classmethod
    def from_env(cls, prefix: str = "PYPOS_", **overrides: Any) -> POSConfig:
        """Build a config from ``PYPOS_*`` environment variables."""
        values: dict[str, Any] = {}
        for name in cls.model_fields:
            raw = os.environ.get(prefix + name.upper())
            if raw is None:
                continue
            if name in {"receipt_header", "receipt_footer"}:
                values[name] = tuple(x for x in raw.split("|") if x)
            else:
                values[name] = raw
        values.update(overrides)
        try:
            return cls(**values)
        except Exception as exc:
            raise ConfigurationError(f"invalid configuration: {exc}") from exc

    def redacted(self) -> dict[str, Any]:
        """Safe-to-print view (secrets and DB passwords masked)."""
        data = self.model_dump(mode="json")
        if data.get("secret_key"):
            data["secret_key"] = "********"
        data["database_url"] = _mask_url(data["database_url"])
        return data

    def __repr_args__(self) -> Any:
        for key, value in super().__repr_args__():
            yield key, (_mask_url(value) if key == "database_url" else value)
