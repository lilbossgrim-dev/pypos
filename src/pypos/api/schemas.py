"""Request/response schemas for the HTTP API (Pydantic only; no FastAPI needed to import)."""

from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

Amount = Annotated[Decimal, Field(max_digits=18, decimal_places=4)]
Qty = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6)]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginIn(_In):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=1024)
    merchant_id: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ProductCreate(_In):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    price: Amount
    cost: Amount = Decimal("0")
    unit: str = "pza"
    barcodes: list[str] = []
    category_id: str | None = None
    tax_codes: list[str] = []
    tax_exempt: bool = False
    track_inventory: bool = True
    description: str = ""


class ProductUpdate(_In):
    name: str | None = None
    description: str | None = None
    price: Amount | None = None
    cost: Amount | None = None
    category_id: str | None = None
    tax_codes: list[str] | None = None
    tax_exempt: bool | None = None
    barcodes: list[str] | None = None


class ProductOut(BaseModel):
    id: str
    sku: str
    name: str
    description: str
    unit: str
    price: str
    cost: str
    currency: str
    barcodes: list[str]
    tax_codes: list[str]
    tax_exempt: bool
    track_inventory: bool
    active: bool
    category_id: str | None = None
    parent_id: str | None = None


class StockReceiveIn(_In):
    product_id: str
    warehouse_id: str
    quantity: Qty
    reason: str = ""


class StockAdjustIn(_In):
    product_id: str
    warehouse_id: str
    delta: Decimal | None = None
    new_quantity: Decimal | None = None
    reason: str = Field(min_length=1)


class CartCreate(_In):
    customer_id: str | None = None
    notes: str = ""


class LineIn(_In):
    product_id: str | None = None
    sku: str | None = None
    barcode: str | None = None
    quantity: Qty = Decimal("1")


class PaymentIn(_In):
    method: str = Field(min_length=1)
    amount: Amount
    tendered: Amount | None = None
    reference: str | None = None


class ConfirmIn(_In):
    payments: list[PaymentIn]


class CancelIn(_In):
    reason: str = Field(min_length=1)


class CashOpenIn(_In):
    opening_float: Amount = Decimal("0")
    notes: str = ""


class CashCloseIn(_In):
    counted: Amount
    notes: str = ""


class ReturnLineIn(_In):
    line_id: str
    quantity: Qty


class ReturnIn(_In):
    sale_id: str
    items: list[ReturnLineIn] = Field(min_length=1)
    reason: str = Field(min_length=1)
    restock: bool = True


class AuthorizeIn(_In):
    approve: bool = True
    note: str = ""


class PageOut(BaseModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    pages: int


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorOut(BaseModel):
    error: ErrorBody
