import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, get_current_user, get_db, require_permission
from app.core.rbac import Permission
from app.schemas.common import CostParamsIn, CostSummaryOut
from app.services.audit import log_action
from app.services.cost_engine import CostParams, recalculate_project_cost
from app.services.reports import build_boq_xlsx

router = APIRouter(prefix="/v1/projects", tags=["cost"])


@router.get("/{project_id}/cost", response_model=CostSummaryOut)
def get_cost(
    project_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CostSummaryOut:
    summary = recalculate_project_cost(
        db, organization_id=uuid.UUID(user.organization_id), project_id=project_id
    )
    db.commit()
    return CostSummaryOut(
        direct=summary.direct,
        indirect=summary.indirect,
        contingency=summary.contingency,
        total=summary.total,
        bid_price=summary.bid_price,
        margin_amount=summary.margin_amount,
        cost_per_m2=summary.cost_per_m2,
        by_category=summary.by_category,
        line_count=summary.line_count,
        priced_count=summary.priced_count,
        unpriced_categories=summary.unpriced_categories,
    )


@router.post("/{project_id}/cost/recalculate", response_model=CostSummaryOut)
def recalc_cost(
    project_id: uuid.UUID,
    params: CostParamsIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CostSummaryOut:
    summary = recalculate_project_cost(
        db,
        organization_id=uuid.UUID(user.organization_id),
        project_id=project_id,
        params=CostParams(
            indirect_pct=params.indirect_pct,
            contingency_pct=params.contingency_pct,
            margin_pct=params.margin_pct,
        ),
    )
    log_action(
        db,
        organization_id=user.organization_id,
        user_id=user.user_id,
        action="recalculate_cost",
        entity_type="project",
        entity_id=project_id,
        after={
            "total": float(summary.total),
            "bid_price": float(summary.bid_price),
            "margin_pct": float(params.margin_pct),
        },
    )
    db.commit()
    return CostSummaryOut(
        direct=summary.direct,
        indirect=summary.indirect,
        contingency=summary.contingency,
        total=summary.total,
        bid_price=summary.bid_price,
        margin_amount=summary.margin_amount,
        cost_per_m2=summary.cost_per_m2,
        by_category=summary.by_category,
        line_count=summary.line_count,
        priced_count=summary.priced_count,
        unpriced_categories=summary.unpriced_categories,
    )


@router.get("/{project_id}/reports/boq.xlsx")
def export_boq(
    project_id: uuid.UUID,
    user: CurrentUser = Depends(require_permission(Permission.EXPORT_REPORT)),
    db: Session = Depends(get_db),
) -> Response:
    content = build_boq_xlsx(
        db, organization_id=uuid.UUID(user.organization_id), project_id=project_id
    )
    log_action(
        db,
        organization_id=user.organization_id,
        user_id=user.user_id,
        action="export",
        entity_type="report",
        entity_id=project_id,
        after={"format": "xlsx"},
    )
    db.commit()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="boq_{project_id}.xlsx"'},
    )
