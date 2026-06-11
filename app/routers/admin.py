from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import require_admin
import uuid

from app.services import plan_service, product_service

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
Session = Annotated[AsyncSession, Depends(get_session)]
Admin = Annotated[str, Depends(require_admin)]


@router.get("", include_in_schema=False)
async def admin_home(_: Admin) -> RedirectResponse:
    return RedirectResponse("/admin/products", status_code=302)


@router.get("/products", response_class=HTMLResponse, include_in_schema=False)
async def products_page(
    request: Request,
    session: Session,
    admin: Admin,
    created: bool = False,
) -> HTMLResponse:
    products = await product_service.list_products(session)
    return templates.TemplateResponse(
        request,
        "admin/products.html",
        {
            "products": products,
            "admin": admin,
            "created": created,
            "generated_token": None,
            "error": None,
        },
    )


@router.post("/products", response_class=HTMLResponse, include_in_schema=False)
async def create_product(
    request: Request,
    session: Session,
    admin: Admin,
    name: Annotated[str, Form(max_length=255)],
    slug: Annotated[str, Form(max_length=100)],
) -> HTMLResponse:
    try:
        _, token = await product_service.create_product(session, name, slug)
    except product_service.ProductAlreadyExists:
        error = "Ja existe um produto com este slug."
    except product_service.InvalidSlug:
        error = "Use apenas letras minusculas, numeros e hifens no slug."
    except ValueError as exc:
        error = str(exc)
    else:
        return templates.TemplateResponse(
            request,
            "admin/products.html",
            {
                "products": await product_service.list_products(session),
                "admin": admin,
                "created": True,
                "generated_token": token,
                "error": None,
            },
            headers={"Cache-Control": "no-store"},
        )

    products = await product_service.list_products(session)
    return templates.TemplateResponse(
        request,
        "admin/products.html",
        {
            "products": products,
            "admin": admin,
            "created": False,
            "error": error,
            "form_name": name,
            "form_slug": slug,
        },
        status_code=422,
    )


@router.post("/products/{product_id}/rotate-token", include_in_schema=False)
async def rotate_product_token(
    request: Request, product_id: uuid.UUID, session: Session, admin: Admin
) -> HTMLResponse:
    try:
        token = await product_service.rotate_service_token(session, product_id)
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "admin/products.html",
            {
                "products": await product_service.list_products(session),
                "admin": admin,
                "created": False,
                "generated_token": None,
                "error": str(exc),
            },
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "admin/products.html",
        {
            "products": await product_service.list_products(session),
            "admin": admin,
            "created": False,
            "generated_token": token,
            "error": None,
        },
        headers={"Cache-Control": "no-store"},
    )


async def _plans_context(
    session: AsyncSession,
    product_id: uuid.UUID | None,
    **extra,
) -> dict:
    products = await plan_service.list_products_with_plans(session)
    selected = (
        next((product for product in products if product.id == product_id), None)
        if product_id
        else (products[0] if products else None)
    )
    if selected:
        selected.plans.sort(key=lambda plan: (plan.position, plan.name))
    return {"products": products, "selected": selected, **extra}


@router.get("/plans", response_class=HTMLResponse, include_in_schema=False)
async def plans_page(
    request: Request,
    session: Session,
    admin: Admin,
    product_id: uuid.UUID | None = None,
    saved: bool = False,
) -> HTMLResponse:
    context = await _plans_context(session, product_id, admin=admin, saved=saved, error=None)
    return templates.TemplateResponse(request, "admin/plans.html", context)


@router.post("/plans", response_class=HTMLResponse, include_in_schema=False)
async def save_plan(
    request: Request,
    session: Session,
    admin: Admin,
    product_id: Annotated[uuid.UUID, Form()],
    name: Annotated[str, Form(max_length=100)],
    slug: Annotated[str, Form(max_length=100)],
    position: Annotated[int, Form()],
    price_cents: Annotated[int, Form()],
    currency: Annotated[str, Form(max_length=3)],
    max_recipes: Annotated[int, Form()],
    max_slots: Annotated[int, Form()],
    max_users: Annotated[int, Form()],
    max_ingredients: Annotated[int, Form()],
    reports: Annotated[str, Form()],
    plan_id: Annotated[uuid.UUID | None, Form()] = None,
    export: Annotated[bool, Form()] = False,
    is_active: Annotated[bool, Form()] = False,
) -> HTMLResponse:
    data = plan_service.PlanInput(
        name=name,
        slug=slug,
        position=position,
        price_cents=price_cents,
        currency=currency,
        max_recipes=max_recipes,
        max_slots=max_slots,
        max_users=max_users,
        max_ingredients=max_ingredients,
        reports=reports,
        export=export,
        is_active=is_active,
    )
    try:
        await plan_service.save_plan(session, product_id, data, plan_id)
    except plan_service.PlanError as exc:
        context = await _plans_context(
            session,
            product_id,
            admin=admin,
            saved=False,
            error=str(exc),
            form=data,
            form_plan_id=plan_id,
        )
        return templates.TemplateResponse(
            request, "admin/plans.html", context, status_code=422
        )
    return RedirectResponse(
        f"/admin/plans?product_id={product_id}&saved=true", status_code=303
    )
