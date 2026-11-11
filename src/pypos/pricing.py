"""Discounts: exact, explicit rounding, never more than the amount discounted."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pypos.exceptions import ValidationError
from pypos.types import Money, to_decimal


class DiscountKind(StrEnum):
    PERCENT = "percent"
    AMOUNT = "amount"


@dataclass(frozen=True)
class Discount:
    kind: DiscountKind
    value: Decimal

    @classmethod
    def percent(cls, pct: Any) -> Discount:
        v = to_decimal(pct, "percent")
        if v < 0 or v > 100:
            raise ValidationError("percent discount must be between 0 and 100")
        return cls(DiscountKind.PERCENT, v)

    @classmethod
    def amount(cls, value: Any) -> Discount:
        v = to_decimal(value, "amount")
        if v < 0:
            raise ValidationError("discount amount cannot be negative")
        return cls(DiscountKind.AMOUNT, v)

    def apply_to(self, gross: Money, rounding: str) -> Money:
        """Return the discount as Money, capped at ``gross``."""
        if self.kind is DiscountKind.PERCENT:
            d = gross.percent(self.value, rounding)
        else:
            d = Money.of(self.value, gross.currency, rounding)
        return min(d, gross, key=lambda m: m.amount)
