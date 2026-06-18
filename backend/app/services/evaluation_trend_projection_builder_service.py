from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Callable

from app.models.evaluation_trend_projection import (
    EvaluationTrendBucket,
    EvaluationTrendDimensionBucket,
)
from app.models.projection import (
    ProjectionMetadata,
    ProjectionReconstructionInfo,
    ProjectionSchemaInfo,
)
from app.services.base_projection_builder import BaseProjectionBuilder
from app.services.evaluation_service import (
    EvaluationService,
    EvaluationTargetSnapshotNotFoundError,
    evaluation_service,
)


EVALUATION_TREND_PROJECTION_TYPE = "evaluation_trend"
EVALUATION_TREND_SCHEMA_VERSION = 1
EVALUATION_TREND_SOURCE = "evaluation_trend_projection_builder"
DEFAULT_EVALUATION_TREND_GRANULARITY = "day"
VALID_EVALUATION_TREND_GRANULARITIES = {"day", "week", "month"}


class EvaluationTrendProjectionBuilderService(
    BaseProjectionBuilder[dict[str, str | None], list[EvaluationTrendBucket]]
):
    schema_info = ProjectionSchemaInfo(
        projection_type=EVALUATION_TREND_PROJECTION_TYPE,
        schema_version=EVALUATION_TREND_SCHEMA_VERSION,
        builder_name="EvaluationTrendProjectionBuilderService",
        reconstruction=ProjectionReconstructionInfo(
            projection_type=EVALUATION_TREND_PROJECTION_TYPE,
            reconstruction_source="evaluation_state",
            authoritative_source="evaluations/results/target_snapshots",
        ),
    )
    projection_type = EVALUATION_TREND_PROJECTION_TYPE

    def __init__(
        self,
        evaluations: EvaluationService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._evaluations = evaluations or evaluation_service
        self._clock = clock or (lambda: datetime.now(UTC))

    def build(
        self,
        source: dict[str, str | None],
    ) -> list[EvaluationTrendBucket]:
        granularity = source.get("granularity") or DEFAULT_EVALUATION_TREND_GRANULARITY
        if granularity not in VALID_EVALUATION_TREND_GRANULARITIES:
            granularity = DEFAULT_EVALUATION_TREND_GRANULARITY

        from_date = _parse_optional_datetime(source.get("from_date"))
        to_date = _parse_optional_datetime(source.get("to_date"))
        dimension_filter = source.get("dimension_id")
        target_type_filter = source.get("target_type")

        records = self._evaluations.list_evaluations(
            session_id=source.get("session_id"),
            decision_id=source.get("decision_id"),
            artifact_id=source.get("artifact_id"),
            evaluation_type=source.get("evaluation_type"),
            status=source.get("status"),
        )
        grouped: dict[tuple[str, str], dict[str, object]] = {}

        for record in records:
            created_at = _as_utc(record.created_at)
            if from_date is not None and created_at < from_date:
                continue
            if to_date is not None and created_at > to_date:
                continue

            try:
                snapshot = self._evaluations.get_target_snapshot(record.id)
                target_type = snapshot.target_type
            except EvaluationTargetSnapshotNotFoundError:
                target_type = None

            if target_type_filter is not None and target_type != target_type_filter:
                continue

            bucket_start, bucket_end = _bucket_window(created_at, granularity)
            key = (bucket_start.isoformat(), bucket_end.isoformat())
            state = grouped.setdefault(
                key,
                {
                    "bucket_start": bucket_start,
                    "bucket_end": bucket_end,
                    "evaluation_count": 0,
                    "scores": [],
                    "target_types": set(),
                    "evaluation_types": set(),
                    "dimension_scores": defaultdict(list),
                    "dimension_names": {},
                },
            )
            state["evaluation_count"] = int(state["evaluation_count"]) + 1
            evaluation_types = state["evaluation_types"]
            assert isinstance(evaluation_types, set)
            evaluation_types.add(record.evaluation_type)
            target_types = state["target_types"]
            assert isinstance(target_types, set)
            if target_type is not None:
                target_types.add(target_type)

            results = self._evaluations.get_results(record.id)
            for result in results:
                if (
                    dimension_filter is not None
                    and result.dimension_id != dimension_filter
                ):
                    continue
                score = float(result.score)
                scores = state["scores"]
                assert isinstance(scores, list)
                scores.append(score)
                dimension_scores = state["dimension_scores"]
                assert isinstance(dimension_scores, defaultdict)
                dimension_scores[result.dimension_id].append(score)
                dimension_names = state["dimension_names"]
                assert isinstance(dimension_names, dict)
                dimension_names[result.dimension_id] = (
                    self._evaluations.get_dimension(result.dimension_id).name
                )

        metadata = ProjectionMetadata(
            **self.schema_info.model_dump(),
            built_at=self._clock(),
            source=EVALUATION_TREND_SOURCE,
        )
        buckets: list[EvaluationTrendBucket] = []
        for _, state in sorted(grouped.items()):
            scores = state["scores"]
            assert isinstance(scores, list)
            target_types = state["target_types"]
            assert isinstance(target_types, set)
            evaluation_types = state["evaluation_types"]
            assert isinstance(evaluation_types, set)
            dimension_scores = state["dimension_scores"]
            assert isinstance(dimension_scores, defaultdict)
            dimension_names = state["dimension_names"]
            assert isinstance(dimension_names, dict)

            buckets.append(
                EvaluationTrendBucket(
                    metadata=metadata.model_copy(deep=True),
                    bucket_start=state["bucket_start"].isoformat(),
                    bucket_end=state["bucket_end"].isoformat(),
                    bucket_granularity=granularity,
                    evaluation_count=int(state["evaluation_count"]),
                    result_count=len(scores),
                    average_score=(sum(scores) / len(scores) if scores else None),
                    min_score=min(scores) if scores else None,
                    max_score=max(scores) if scores else None,
                    target_types=sorted(target_types),
                    evaluation_types=sorted(evaluation_types),
                    dimensions=[
                        EvaluationTrendDimensionBucket(
                            dimension_id=dimension_id,
                            dimension_name=dimension_names[dimension_id],
                            result_count=len(dimension_scores[dimension_id]),
                            average_score=(
                                sum(dimension_scores[dimension_id])
                                / len(dimension_scores[dimension_id])
                            ),
                            min_score=min(dimension_scores[dimension_id]),
                            max_score=max(dimension_scores[dimension_id]),
                        )
                        for dimension_id in sorted(dimension_scores)
                    ],
                )
            )
        return buckets


def _parse_optional_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _bucket_window(
    occurred_at: datetime,
    granularity: str,
) -> tuple[datetime, datetime]:
    occurred = _as_utc(occurred_at)
    if granularity == "day":
        start = occurred.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return start, end
    if granularity == "week":
        start = (
            occurred.replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(days=occurred.weekday())
        )
        end = start + timedelta(days=7)
        return start, end
    start = occurred.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


evaluation_trend_projection_builder_service = (
    EvaluationTrendProjectionBuilderService()
)
