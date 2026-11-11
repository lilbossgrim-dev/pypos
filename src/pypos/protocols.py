"""Extension contracts implemented by third parties (payment adapters, clocks)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from pypos.types import Money


@dataclass(frozen=True)
class ChargeRequest:
    payment_id: str  # use as the provider-side idempotency key
    amount: Money
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RefundRequest:
    payment_id: str
    refund_id: str  # provider-side idempotency key
    amount: Money
    external_ref: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class AdapterResult:
    success: bool
    external_ref: str | None = None
    error: str | None = None


@runtime_checkable
class PaymentAdapter(Protocol):
    """Gateway to an external payment system.

    ``charge``/``refund`` must be idempotent for the same ``payment_id`` /
    ``refund_id``. Raising an exception means *unknown outcome* (e.g. timeout);
    returning ``AdapterResult(success=False)`` means a definite decline.
    """

    name: str
    sandbox: bool

    def charge(self, request: ChargeRequest) -> AdapterResult: ...

    def refund(self, request: RefundRequest) -> AdapterResult: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
