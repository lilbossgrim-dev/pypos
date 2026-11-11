"""FastAPI application factory. Endpoints only translate HTTP <-> service calls;
all business rules live in the services (no rules are duplicated here)."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse

from pypos import __version__
from pypos.api import schemas as s
from pypos.application import POS
from pypos.core.codec import to_dict
from pypos.core.context import OperationContext
from pypos.exceptions import AuthenticationError, PyPOSError
from pypos.payments import PaymentRequest
from pypos.returns import ReturnItem
from pypos.types import Page


def _page(page: Page[Any]) -> dict[str, Any]:
    return {"items": [to_dict(i) for i in page.items], "total": page.total,
            "page": page.page, "page_size": page.page_size, "pages": page.pages}  # fmt: skip


def _product(p: Any) -> dict[str, Any]:
    return s.ProductOut(
        id=p.id, sku=p.sku, name=p.name, description=p.description, unit=p.unit,
        price=str(p.price.amount), cost=str(p.cost.amount), currency=p.price.currency,
        barcodes=p.barcodes, tax_codes=p.tax_codes, tax_exempt=p.tax_exempt,
        track_inventory=p.track_inventory, active=p.active, category_id=p.category_id,
        parent_id=p.parent_id,
    ).model_dump()  # fmt: skip


def context_dependency(pos: POS) -> Any:
    """FastAPI dependency returning the caller's OperationContext (Bearer token).

    Plugins that add routes should ``Depends(context_dependency(pos))`` too.
    """

    def get_context(
        authorization: str | None = Header(default=None),
        x_branch_id: str | None = Header(default=None),
        x_terminal_id: str | None = Header(default=None),
    ) -> OperationContext:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise AuthenticationError("missing bearer token")
        return pos.users.context_from_token(
            authorization[7:].strip(), branch_id=x_branch_id, terminal_id=x_terminal_id
        )

    return get_context


def create_app(pos: POS, *, title: str = "PyPOS API") -> FastAPI:
    app = FastAPI(title=title, version=__version__, docs_url="/docs", openapi_url="/openapi.json")
    ctx_dep = context_dependency(pos)
    v1 = APIRouter(prefix="/v1")

    #errors
    @app.exception_handler(PyPOSError)
    async def _pypos_error(_: Request, exc: PyPOSError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.http_status == 401 else None
        return JSONResponse({"error": exc.to_dict()}, status_code=exc.http_status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        body = {
            "code": "invalid_request",
            "message": "request validation failed",
            "details": {"errors": errors},
        }
        return JSONResponse({"error": body}, status_code=422)

    @app.exception_handler(TypeError)
    async def _type_error(_: Request, exc: TypeError) -> JSONResponse:
        body = {"code": "validation_error", "message": str(exc), "details": {}}
        return JSONResponse({"error": body}, status_code=422)

    #health
    @app.get("/health", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def ready() -> JSONResponse:
        h = pos.health()
        return JSONResponse(h, status_code=200 if h["status"] == "ok" else 503)

    #auth
    @v1.post("/auth/login", response_model=s.TokenOut, tags=["auth"])
    def login(body: s.LoginIn) -> s.TokenOut:
        token = pos.users.login(body.username, body.password, body.merchant_id)
        return s.TokenOut(access_token=token, expires_in=pos.config.token_ttl_seconds)

    #products
    @v1.get("/products", response_model=s.PageOut, tags=["products"])
    def list_products(
        q: str = "", page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
        include_inactive: bool = False, ctx: OperationContext = Depends(ctx_dep),
    ) -> dict[str, Any]:  # fmt: skip
        result = pos.products.search(ctx, q, active=None if include_inactive else True,
                                     page=page, page_size=page_size)  # fmt: skip
        return {"items": [_product(p) for p in result.items], "total": result.total,
                "page": result.page, "page_size": result.page_size, "pages": result.pages}  # fmt: skip

    @v1.post("/products", response_model=s.ProductOut, status_code=201, tags=["products"])
    def create_product(
        body: s.ProductCreate, ctx: OperationContext = Depends(ctx_dep)
    ) -> dict[str, Any]:
        p = pos.products.create(ctx, body.sku, body.name, body.price, body.cost, unit=body.unit,
                                barcodes=body.barcodes, category_id=body.category_id,
                                tax_codes=body.tax_codes, tax_exempt=body.tax_exempt,
                                track_inventory=body.track_inventory, description=body.description)  # fmt: skip
        return _product(p)

    @v1.get("/products/{product_id}", response_model=s.ProductOut, tags=["products"])
    def get_product(product_id: str, ctx: OperationContext = Depends(ctx_dep)) -> dict[str, Any]:
        return _product(pos.products.get(ctx, product_id))

    @v1.patch("/products/{product_id}", response_model=s.ProductOut, tags=["products"])
    def update_product(product_id: str, body: s.ProductUpdate,
                       ctx: OperationContext = Depends(ctx_dep)) -> dict[str, Any]:  # fmt: skip
        return _product(pos.products.update(ctx, product_id, **body.model_dump(exclude_unset=True)))

    @v1.post("/products/{product_id}/deactivate", response_model=s.ProductOut, tags=["products"])
    def deactivate_product(
        product_id: str, ctx: OperationContext = Depends(ctx_dep)
    ) -> dict[str, Any]:
        return _product(pos.products.deactivate(ctx, product_id))

    #inventory
    @v1.get("/inventory/stock", tags=["inventory"])
    def stock(
        product_id: str, warehouse_id: str, ctx: OperationContext = Depends(ctx_dep)
    ) -> dict[str, str]:
        return {"product_id": product_id, "warehouse_id": warehouse_id,
                "quantity": str(pos.inventory.stock_of(ctx, product_id, warehouse_id))}  # fmt: skip

    @v1.post("/inventory/receive", status_code=201, tags=["inventory"])
    def receive(body: s.StockReceiveIn, ctx: OperationContext = Depends(ctx_dep),
                idempotency_key: str | None = Header(default=None)) -> dict[str, Any]:  # fmt: skip
        m = pos.inventory.receive(ctx, body.product_id, body.warehouse_id, body.quantity,
                                  reason=body.reason, idempotency_key=idempotency_key)  # fmt: skip
        return to_dict(m)

    @v1.post("/inventory/adjust", status_code=201, tags=["inventory"])
    def adjust(body: s.StockAdjustIn, ctx: OperationContext = Depends(ctx_dep),
               idempotency_key: str | None = Header(default=None)) -> dict[str, Any]:  # fmt: skip
        m = pos.inventory.adjust(ctx, body.product_id, body.warehouse_id, delta=body.delta,
                                 new_quantity=body.new_quantity, reason=body.reason,
                                 idempotency_key=idempotency_key)  # fmt: skip
        return to_dict(m)

    #sales
    @v1.post("/sales", status_code=201, tags=["sales"])
    def create_cart(body: s.CartCreate, ctx: OperationContext = Depends(ctx_dep)) -> dict[str, Any]:
        return to_dict(pos.sales.create_cart(ctx, customer_id=body.customer_id, notes=body.notes))

    @v1.get("/sales", response_model=s.PageOut, tags=["sales"])
    def list_sales(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                   ctx: OperationContext = Depends(ctx_dep)) -> dict[str, Any]:  # fmt: skip
        return _page(pos.sales.list(ctx, page=page, page_size=page_size))

    @v1.get("/sales/{sale_id}", tags=["sales"])
    def get_sale(sale_id: str, ctx: OperationContext = Depends(ctx_dep)) -> dict[str, Any]:
        return to_dict(pos.sales.get(ctx, sale_id))

    @v1.post("/sales/{sale_id}/lines", tags=["sales"])
    def add_line(
        sale_id: str, body: s.LineIn, ctx: OperationContext = Depends(ctx_dep)
    ) -> dict[str, Any]:
        sale = pos.sales.add_line(ctx, sale_id, product_id=body.product_id, sku=body.sku,
                                  barcode=body.barcode, quantity=body.quantity)  # fmt: skip
        return to_dict(sale)

    @v1.delete("/sales/{sale_id}/lines/{line_id}", tags=["sales"])
    def remove_line(
        sale_id: str, line_id: str, ctx: OperationContext = Depends(ctx_dep)
    ) -> dict[str, Any]:
        return to_dict(pos.sales.remove_line(ctx, sale_id, line_id))

    @v1.post("/sales/{sale_id}/confirm", tags=["sales"])
    def confirm(sale_id: str, body: s.ConfirmIn, ctx: OperationContext = Depends(ctx_dep),
                idempotency_key: str | None = Header(default=None)) -> dict[str, Any]:  # fmt: skip
        reqs = [PaymentRequest(p.method, p.amount, p.tendered, p.reference) for p in body.payments]
        return to_dict(pos.sales.confirm(ctx, sale_id, reqs, idempotency_key=idempotency_key))

    @v1.post("/sales/{sale_id}/cancel", tags=["sales"])
    def cancel(
        sale_id: str, body: s.CancelIn, ctx: OperationContext = Depends(ctx_dep)
    ) -> dict[str, Any]:
        return to_dict(pos.sales.cancel(ctx, sale_id, body.reason))

    @v1.get("/sales/{sale_id}/receipt", response_class=PlainTextResponse, tags=["sales"])
    def receipt(sale_id: str, ctx: OperationContext = Depends(ctx_dep)) -> str:
        return pos.sales.receipt(ctx, sale_id)

    #cash
    @v1.post("/cash/open", status_code=201, tags=["cash"])
    def cash_open(body: s.CashOpenIn, ctx: OperationContext = Depends(ctx_dep)) -> dict[str, Any]:
        return to_dict(pos.cash.open(ctx, body.opening_float, body.notes))

    @v1.post("/cash/close", tags=["cash"])
    def cash_close(body: s.CashCloseIn, ctx: OperationContext = Depends(ctx_dep)) -> dict[str, Any]:
        return to_dict(pos.cash.close(ctx, body.counted, body.notes))

    @v1.get("/cash/current", tags=["cash"])
    def cash_current(ctx: OperationContext = Depends(ctx_dep)) -> dict[str, Any]:
        cur = pos.cash.current(ctx)
        return {"session": to_dict(cur) if cur else None}

    #returns
    @v1.post("/returns", status_code=201, tags=["returns"])
    def create_return(body: s.ReturnIn, ctx: OperationContext = Depends(ctx_dep),
                      idempotency_key: str | None = Header(default=None)) -> dict[str, Any]:  # fmt: skip
        items = [ReturnItem(i.line_id, i.quantity) for i in body.items]
        ret = pos.returns.create(ctx, body.sale_id, items, body.reason, restock=body.restock,
                                 idempotency_key=idempotency_key)  # fmt: skip
        return to_dict(ret)

    @v1.post("/returns/{return_id}/authorize", tags=["returns"])
    def authorize_return(return_id: str, body: s.AuthorizeIn,
                         ctx: OperationContext = Depends(ctx_dep)) -> dict[str, Any]:  # fmt: skip
        return to_dict(pos.returns.authorize(ctx, return_id, approve=body.approve, note=body.note))

    #reports
    @v1.get("/reports/sales", tags=["reports"])
    def sales_report(start: datetime | None = None, end: datetime | None = None, group: str = "day",
                     ctx: OperationContext = Depends(ctx_dep)) -> list[dict[str, Any]]:  # fmt: skip
        return pos.reporting.sales_by_period(ctx, start, end, group)

    app.include_router(v1)
    for factory in pos.plugin_routes:  # routes contributed by plugins
        app.include_router(factory(pos))
    return app


__all__ = ["context_dependency", "create_app"]
