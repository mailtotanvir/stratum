from fastapi import APIRouter, HTTPException, Query

from app.models.operational_analytics import (
    GovernanceAnalytics,
    ProjectionAnalytics,
    ReconstructionAnalytics,
    RuntimeOperationalAnalytics,
    RuntimeTrendAnalytics,
)
from app.services.operational_analytics_service import (
    DEFAULT_TREND_LOOKBACK_DAYS,
    OperationalAnalyticsGenerationError,
    operational_analytics_service,
)


router = APIRouter()


@router.get("/runtime/analytics")
def get_runtime_analytics(
    lookback_days: int = Query(
        default=DEFAULT_TREND_LOOKBACK_DAYS,
        ge=1,
    ),
) -> RuntimeOperationalAnalytics:
    try:
        return operational_analytics_service.generate(
            lookback_days=lookback_days,
        )
    except OperationalAnalyticsGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/runtime/analytics/governance")
def get_runtime_governance_analytics() -> GovernanceAnalytics:
    try:
        return operational_analytics_service.governance()
    except OperationalAnalyticsGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/runtime/analytics/projections")
def get_runtime_projection_analytics() -> ProjectionAnalytics:
    try:
        return operational_analytics_service.projections()
    except OperationalAnalyticsGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/runtime/analytics/reconstruction")
def get_runtime_reconstruction_analytics() -> ReconstructionAnalytics:
    try:
        return operational_analytics_service.reconstruction()
    except OperationalAnalyticsGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/runtime/analytics/trends")
def get_runtime_trend_analytics(
    lookback_days: int = Query(
        default=DEFAULT_TREND_LOOKBACK_DAYS,
        ge=1,
    ),
) -> RuntimeTrendAnalytics:
    try:
        return operational_analytics_service.trends(lookback_days=lookback_days)
    except OperationalAnalyticsGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
