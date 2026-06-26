from collections import Counter
from datetime import datetime

from app.models.evaluation_drift import (
    EvaluationDriftBaseline,
    EvaluationDriftBaselineCreate,
    EvaluationDriftObservation,
    EvaluationDriftObservationCreate,
    EvaluationDriftProjection,
    EvaluationDriftRecord,
    EvaluationDriftStatus,
)
from app.models.projection import ProjectionMetadata
from app.services.event_service import EventService, event_service


EVALUATION_DRIFT_BASELINE_REGISTERED = (
    "evaluation_drift_baseline_registered"
)
EVALUATION_DRIFT_OBSERVATION_REGISTERED = (
    "evaluation_drift_observation_registered"
)


class EvaluationDriftBaselineAlreadyExistsError(ValueError):
    pass


class EvaluationDriftBaselineNotFoundError(LookupError):
    pass


class EvaluationDriftObservationAlreadyExistsError(ValueError):
    pass


class EvaluationDriftObservationNotFoundError(LookupError):
    pass


class EvaluationDriftService:
    def __init__(
        self,
        events: EventService | None = None,
    ) -> None:
        self._events = events or event_service

    def register_baseline(
        self,
        request: EvaluationDriftBaselineCreate,
    ) -> EvaluationDriftBaseline:
        baselines = self.list_baselines()
        baseline_id = request.baseline_id or f"drift-baseline-{len(baselines) + 1}"
        if baseline_id in {baseline.baseline_id for baseline in baselines}:
            raise EvaluationDriftBaselineAlreadyExistsError(
                f"Evaluation drift baseline already registered: {baseline_id}"
            )

        event = self._events.emit_event_sync(
            event_type=EVALUATION_DRIFT_BASELINE_REGISTERED,
            message="Evaluation drift baseline registered",
            metadata={
                **request.model_dump(exclude={"baseline_id"}),
                "baseline_id": baseline_id,
            },
        )
        return _baseline_from_event_metadata(event.metadata, event.ts)

    def register_observation(
        self,
        request: EvaluationDriftObservationCreate,
    ) -> EvaluationDriftObservation:
        observations = self.list_observations()
        observation_id = (
            request.observation_id
            or f"drift-observation-{len(observations) + 1}"
        )
        if observation_id in {
            observation.observation_id
            for observation in observations
        }:
            raise EvaluationDriftObservationAlreadyExistsError(
                "Evaluation drift observation already registered: "
                f"{observation_id}"
            )

        event = self._events.emit_event_sync(
            event_type=EVALUATION_DRIFT_OBSERVATION_REGISTERED,
            message="Evaluation drift observation registered",
            metadata={
                **request.model_dump(exclude={"observation_id"}),
                "observation_id": observation_id,
            },
        )
        return _observation_from_event_metadata(event.metadata, event.ts)

    def get_baseline(self, baseline_id: str) -> EvaluationDriftBaseline:
        for baseline in self.list_baselines():
            if baseline.baseline_id == baseline_id:
                return baseline
        raise EvaluationDriftBaselineNotFoundError(
            f"Evaluation drift baseline not found: {baseline_id}"
        )

    def list_baselines(self) -> list[EvaluationDriftBaseline]:
        return sorted(
            [
                _baseline_from_event_metadata(event.metadata, event.ts)
                for event in self._events.list_persisted_events(
                    event_type=EVALUATION_DRIFT_BASELINE_REGISTERED
                )
            ],
            key=lambda baseline: (baseline.created_at, baseline.baseline_id),
        )

    def get_observation(
        self,
        observation_id: str,
    ) -> EvaluationDriftObservation:
        for observation in self.list_observations():
            if observation.observation_id == observation_id:
                return observation
        raise EvaluationDriftObservationNotFoundError(
            f"Evaluation drift observation not found: {observation_id}"
        )

    def list_observations(self) -> list[EvaluationDriftObservation]:
        return sorted(
            [
                _observation_from_event_metadata(event.metadata, event.ts)
                for event in self._events.list_persisted_events(
                    event_type=EVALUATION_DRIFT_OBSERVATION_REGISTERED
                )
            ],
            key=lambda observation: (
                observation.observed_at,
                observation.observation_id,
            ),
        )

    def build_projection(
        self,
        *,
        metadata: ProjectionMetadata,
        generated_at: datetime,
    ) -> EvaluationDriftProjection:
        baselines = self.list_baselines()
        observations = self.list_observations()
        drift_records = _build_drift_records(baselines, observations)
        counts = Counter(record.drift_status for record in drift_records)
        return EvaluationDriftProjection(
            metadata=metadata,
            baselines=baselines,
            observations=observations,
            drift_records=drift_records,
            total_baselines=len(baselines),
            total_observations=len(observations),
            total_drift_records=len(drift_records),
            regressed_count=counts["regressed"],
            improved_count=counts["improved"],
            unchanged_count=counts["unchanged"],
            generated_at=generated_at,
        )


def _build_drift_records(
    baselines: list[EvaluationDriftBaseline],
    observations: list[EvaluationDriftObservation],
) -> list[EvaluationDriftRecord]:
    latest_baseline_by_key: dict[
        tuple[str, int],
        EvaluationDriftBaseline,
    ] = {}
    for baseline in baselines:
        latest_baseline_by_key[
            (baseline.evaluation_id, baseline.evaluation_version)
        ] = baseline

    records: list[EvaluationDriftRecord] = []
    for observation in observations:
        baseline = latest_baseline_by_key.get(
            (observation.evaluation_id, observation.evaluation_version)
        )
        if baseline is None:
            continue
        score_delta = observation.observed_score - baseline.baseline_score
        records.append(
            EvaluationDriftRecord(
                drift_id=f"drift-{observation.observation_id}",
                evaluation_id=observation.evaluation_id,
                evaluation_name=observation.evaluation_name,
                evaluation_version=observation.evaluation_version,
                baseline_score=baseline.baseline_score,
                observed_score=observation.observed_score,
                score_delta=score_delta,
                baseline_pass_count=baseline.baseline_pass_count,
                observed_pass_count=observation.observed_pass_count,
                baseline_fail_count=baseline.baseline_fail_count,
                observed_fail_count=observation.observed_fail_count,
                drift_status=_drift_status(score_delta),
            )
        )
    return records


def _drift_status(score_delta: float) -> EvaluationDriftStatus:
    if score_delta < 0:
        return "regressed"
    if score_delta > 0:
        return "improved"
    return "unchanged"


def _baseline_from_event_metadata(
    metadata: dict,
    created_at: str,
) -> EvaluationDriftBaseline:
    return EvaluationDriftBaseline(
        baseline_id=str(metadata["baseline_id"]),
        evaluation_id=str(metadata["evaluation_id"]),
        evaluation_name=str(metadata["evaluation_name"]),
        evaluation_version=int(metadata["evaluation_version"]),
        baseline_score=float(metadata["baseline_score"]),
        baseline_pass_count=int(metadata["baseline_pass_count"]),
        baseline_fail_count=int(metadata["baseline_fail_count"]),
        created_at=datetime.fromisoformat(created_at),
    )


def _observation_from_event_metadata(
    metadata: dict,
    observed_at: str,
) -> EvaluationDriftObservation:
    return EvaluationDriftObservation(
        observation_id=str(metadata["observation_id"]),
        evaluation_id=str(metadata["evaluation_id"]),
        evaluation_name=str(metadata["evaluation_name"]),
        evaluation_version=int(metadata["evaluation_version"]),
        observed_score=float(metadata["observed_score"]),
        observed_pass_count=int(metadata["observed_pass_count"]),
        observed_fail_count=int(metadata["observed_fail_count"]),
        observed_at=datetime.fromisoformat(observed_at),
    )


evaluation_drift_service = EvaluationDriftService()
