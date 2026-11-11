"""Core value types: exact money, quantities, identifiers and pagination."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import (
    ROUND_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    ROUND_UP,
    Decimal,
    InvalidOperation,
)
from typing import Any, Generic, TypeVar

from pypos.exceptions import CurrencyMismatchError, ValidationError

T = TypeVar("T")

ROUNDING_MODES = {
    "HALF_UP": ROUND_HALF_UP,
    "HALF_EVEN": ROUND_HALF_EVEN,
    "DOWN": ROUND_DOWN,
    "UP": ROUND_UP,
}

# ISO 4217 minor-unit exponents that differ from the default of 2.
_CURRENCY_EXPONENTS = {
    "JPY": 0, "KRW": 0, "CLP": 0, "VND": 0, "ISK": 0, "PYG": 0, "UGX": 0,
    "BHD": 3, "KWD": 3, "JOD": 3, "OMR": 3, "TND": 3,
}  # fmt: skip

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


def currency_exponent(code: str) -> int:
    return _CURRENCY_EXPONENTS.get(code, 2)


def to_decimal(value: Any, name: str = "value") -> Decimal:
    """Convert int/str/Decimal to Decimal. Floats and bools are rejected on purpose."""
    if isinstance(value, bool | float):
        raise TypeError(f"{name}: float/bool values are not accepted; use int, str or Decimal")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int | str):
        try:
            result = Decimal(str(value).strip())
        except InvalidOperation as exc:
            raise ValidationError(f"{name}: invalid decimal {value!r}") from exc
    else:
        raise TypeError(f"{name}: unsupported type {type(value).__name__}")
    if not result.is_finite():
        raise ValidationError(f"{name}: must be finite")
    return result


@dataclass(frozen=True, slots=True)
class Money:
    """Exact monetary amount, always quantized to the currency's minor unit."""

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError("Money.amount must be Decimal; use Money.of(...)")
        if not _CURRENCY_RE.match(self.currency):
            raise ValidationError(f"invalid currency code {self.currency!r}")
        exp = Decimal(1).scaleb(-currency_exponent(self.currency))
        if self.amount != self.amount.quantize(exp):
            raise ValidationError(
                "amount has more precision than the currency allows; use Money.of(...)"
            )

    #construction
    @classmethod
    def of(cls, amount: Any, currency: str, rounding: str = ROUND_HALF_UP) -> Money:
        value = to_decimal(amount, "amount")
        exp = Decimal(1).scaleb(-currency_exponent(currency))
        return cls(value.quantize(exp, rounding=rounding), currency)

    @classmethod
    def zero(cls, currency: str) -> Money:
        return cls.of(0, currency)

    @classmethod
    def from_minor(cls, minor: int, currency: str) -> Money:
        return cls.of(Decimal(minor).scaleb(-currency_exponent(currency)), currency)

    @classmethod
    def sum(cls, items: Iterable[Money], currency: str) -> Money:
        total = cls.zero(currency)
        for item in items:
            total = total + item
        return total

    #arithmetic
    def _check(self, other: Money) -> None:
        if not isinstance(other, Money):
            raise TypeError("operands must be Money")
        if other.currency != self.currency:
            raise CurrencyMismatchError(f"cannot combine {self.currency} and {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    def __abs__(self) -> Money:
        return Money(abs(self.amount), self.currency)

    def __mul__(self, factor: int) -> Money:
        if isinstance(factor, bool) or not isinstance(factor, int):
            raise TypeError("use Money.times(factor, rounding) for non-integer factors")
        return Money(self.amount * factor, self.currency)

    __rmul__ = __mul__

    def times(self, factor: Any, rounding: str = ROUND_HALF_UP) -> Money:
        """Multiply by a Decimal/int/str factor with explicit rounding."""
        return Money.of(self.amount * to_decimal(factor, "factor"), self.currency, rounding)

    def percent(self, pct: Any, rounding: str = ROUND_HALF_UP) -> Money:
        """``pct`` percent of this amount (``pct=10`` means 10 %)."""
        return Money.of(self.amount * to_decimal(pct, "pct") / 100, self.currency, rounding)

    def allocate(self, ratios: Sequence[Any]) -> list[Money]:
        """Split without losing a cent (largest-remainder method)."""
        rs = [to_decimal(r, "ratio") for r in ratios]
        if not rs or any(r < 0 for r in rs) or sum(rs) == 0:
            raise ValidationError("ratios must be non-negative with a positive sum")
        total_minor = self.to_minor()
        sign = -1 if total_minor < 0 else 1
        remaining = abs(total_minor)
        denom = sum(rs)
        exact = [Decimal(remaining) * r / denom for r in rs]
        floors = [int(e) for e in exact]
        left = remaining - sum(floors)
        order = sorted(range(len(rs)), key=lambda i: (exact[i] - floors[i], -i), reverse=True)
        for i in order[:left]:
            floors[i] += 1
        return [Money.from_minor(sign * f, self.currency) for f in floors]

    def split(self, parts: int) -> list[Money]:
        if parts <= 0:
            raise ValidationError("parts must be positive")
        return self.allocate([1] * parts)

    #comparison
    def __lt__(self, other: Money) -> bool:
        self._check(other)
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._check(other)
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        self._check(other)
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        self._check(other)
        return self.amount >= other.amount

    def is_zero(self) -> bool:
        return self.amount == 0

    def is_negative(self) -> bool:
        return self.amount < 0

    def is_positive(self) -> bool:
        return self.amount > 0

    #conversion
    def to_minor(self) -> int:
        return int(self.amount.scaleb(currency_exponent(self.currency)))

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"

    def to_dict(self) -> dict[str, str]:
        return {"amount": str(self.amount), "currency": self.currency}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Money:
        return cls.of(data["amount"], data["currency"])


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


def quantity(value: Any, name: str = "quantity", *, allow_zero: bool = False) -> Decimal:
    """Validate a quantity: finite Decimal, positive (or zero when allowed)."""
    q = to_decimal(value, name)
    if q < 0 or (q == 0 and not allow_zero):
        raise ValidationError(f"{name} must be {'non-negative' if allow_zero else 'positive'}")
    return q


@dataclass(frozen=True, slots=True)
class Page(Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        return max(1, -(-self.total // self.page_size))


def paginate(items: Sequence[T], page: int = 1, page_size: int = 50) -> Page[T]:
    if page < 1 or not (1 <= page_size <= 1000):
        raise ValidationError("page must be >= 1 and 1 <= page_size <= 1000")
    start = (page - 1) * page_size
    return Page(list(items[start : start + page_size]), len(items), page, page_size)
