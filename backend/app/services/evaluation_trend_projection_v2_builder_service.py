from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Callable

from app.models.evaluation_trend_projection import (
    EvaluationTrendOutcomeBucket,
    EvaluationTrendProjection,
)
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.evaluation_outcome_rollup_projection_builder_service import (
    SUPPORTED_OUTCOMES,
)
from app.services.evaluation_record_service import (
    EvaluationRecordService,
    evaluation_record_service,
)


EVALUATION_TREND_PROJECTION_TYPE = "evaluation_trend"
EVALUATION_TREND_SCHEMA_VERSION = 1
EVALUATION_TREND_SOURCE = "evaluation_trend_projection_builder"
DEFAULT_EVALUATION_TREND_GRANULARITY = "day"
VALID_EVALUATION_TREND_GRANULARITIES = {"day"}


class EvaluationTrendProjectionBuilderService(
    BaseProjectionBuilder[dict[str, str | None] | None, EvaluationTrendProjection]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=EVALUATION_TREND_PROJECTION_TYPE,
        schema_version=EVALUATION_TREND_SCHEMA_VERSION,
        builder_name="EvaluationTrendProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=EVALUATION_TREND_PROJECTION_TYPE,
            reconstruction_source="evaluation_records",
            authoritative_source="runtime_evaluation_records",
        ),
    )
    projection_type = EVALUATION_TREND_PROJECTION_TYPE

    def __init__(
        self,
        evaluations: EvaluationRecordService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._evaluations = evaluations or evaluation_record_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def build(
        self,
        source: dict[str, str | None] | None = None,
    ) -> EvaluationTrendProjection:
        filters = source or {}
        granularity = (
            filters.get("granularity") or DEFAULT_EVALUATION_TREND_GRANULARITY
        )
        if granularity not in VALID_EVALUATION_TREND_GRANULARITIES:
            granularity = DEFAULT_EVALUATION_TREND_GRANULARITY

        records = self._evaluations.list_records(
            target_type=filters.get("target_type"),  # type: ignore[arg-type]
            target_id=filters.get("target_id"),
            evaluation_type=filters.get("evaluation_type"),
            outcome=filters.get("outcome"),  # type: ignore[arg-type]
        )
        grouped: dict[datetime, list[str]] = defaultdict(list)
        for record in records:
            bucket_start, _ = _bucket_window(record.created_at, granularity)
            grouped[bucket_start].append(str(record.outcome))

        generated_at = self._clock()
        return EvaluationTrendProjection(
            metadata=ProjectionMetadata(
                **self.schema_info.model_dump(),
                built_at=generated_at,
                source=EVALUATION_TREND_SOURCE,
            ),
            bucket_granularity=granularity,
            buckets=[
                _build_bucket(bucket_start, outcomes, granularity)
                for bucket_start, outcomes in sorted(grouped.items())
            ],
            generated_at=generated_at,
        )


def _build_bucket(
    bucket_start: datetime,
    outcomes: list[str],
    granularity: str,
) -> EvaluationTrendOutcomeBucket:
    _, bucket_end = _bucket_window(bucket_start, granularity)
    counts = Counter(outcomes)
    supported_counts = Counter(
        outcome for outcome in outcomes if outcome in SUPPORTED_OUTCOMES
    )
    total = len(outcomes)
    return EvaluationTrendOutcomeBucket(
        bucket_start=bucket_start.isoformat(),
        bucket_end=bucket_end.isoformat(),
        total_evaluations=total,
        evaluations_by_outcome=dict(sorted(counts.items())),
        success_rate=_rate(supported_counts["success"], total),
        failure_rate=_rate(supported_counts["failure"], total),
        acceptance_rate=_rate(supported_counts["accepted"], total),
        rejection_rate=_rate(supported_counts["rejected"], total),
        reversion_rate=_rate(supported_counts["reverted"], total),
        inconclusive_rate=_rate(supported_counts["inconclusive"], total),
    )


def _bucket_window(
    occurred_at: datetime,
    granularity: str,
) -> tuple[datetime, datetime]:
    occurred = _as_utc(occurred_at)
    start = occurred.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _rate(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return count / total


evaluation_trend_projection_builder_service = (
    EvaluationTrendProjectionBuilderService()
)
