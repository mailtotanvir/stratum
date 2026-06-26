from datetime import datetime

from app.models.evaluation_lineage import (
    EvaluationEvidenceRecord,
    EvaluationEvidenceRecordCreate,
    EvaluationLineageProjection,
    EvaluationLineageRecord,
    EvaluationLineageRecordCreate,
)
from app.models.projection import ProjectionMetadata
from app.services.event_service import EventService, event_service


EVALUATION_LINEAGE_RECORDED = "evaluation_lineage_recorded"
EVALUATION_LINEAGE_EVIDENCE_RECORDED = (
    "evaluation_lineage_evidence_recorded"
)


class EvaluationLineageAlreadyExistsError(ValueError):
    pass


class EvaluationLineageNotFoundError(LookupError):
    pass


class EvaluationEvidenceAlreadyExistsError(ValueError):
    pass


class EvaluationEvidenceNotFoundError(LookupError):
    pass


class EvaluationLineageService:
    def __init__(
        self,
        events: EventService | None = None,
    ) -> None:
        self._events = events or event_service

    def register_lineage(
        self,
        request: EvaluationLineageRecordCreate,
    ) -> EvaluationLineageRecord:
        records = self.list_lineage()
        lineage_id = request.lineage_id or f"evaluation-lineage-{len(records) + 1}"
        if lineage_id in {record.lineage_id for record in records}:
            raise EvaluationLineageAlreadyExistsError(
                f"Evaluation lineage already registered: {lineage_id}"
            )

        event = self._events.emit_event_sync(
            event_type=EVALUATION_LINEAGE_RECORDED,
            message="Evaluation lineage recorded",
            metadata={
                **request.model_dump(exclude={"lineage_id"}),
                "lineage_id": lineage_id,
            },
        )
        return _lineage_from_event_metadata(event.metadata, event.ts)

    def register_evidence(
        self,
        request: EvaluationEvidenceRecordCreate,
    ) -> EvaluationEvidenceRecord:
        evidence_records = self.list_evidence()
        evidence_id = (
            request.evidence_id
            or f"evaluation-evidence-{len(evidence_records) + 1}"
        )
        if evidence_id in {
            evidence.evidence_id
            for evidence in evidence_records
        }:
            raise EvaluationEvidenceAlreadyExistsError(
                f"Evaluation evidence already registered: {evidence_id}"
            )
        if request.lineage_id not in {
            record.lineage_id
            for record in self.list_lineage()
        }:
            raise EvaluationLineageNotFoundError(
                f"Evaluation lineage not found: {request.lineage_id}"
            )

        event = self._events.emit_event_sync(
            event_type=EVALUATION_LINEAGE_EVIDENCE_RECORDED,
            message="Evaluation lineage evidence recorded",
            metadata={
                **request.model_dump(exclude={"evidence_id"}),
                "evidence_id": evidence_id,
            },
        )
        return _evidence_from_event_metadata(event.metadata, event.ts)

    def get_lineage(self, lineage_id: str) -> EvaluationLineageRecord:
        for record in self.list_lineage():
            if record.lineage_id == lineage_id:
                return record
        raise EvaluationLineageNotFoundError(
            f"Evaluation lineage not found: {lineage_id}"
        )

    def list_lineage(self) -> list[EvaluationLineageRecord]:
        return sorted(
            [
                _lineage_from_event_metadata(event.metadata, event.ts)
                for event in self._events.list_persisted_events(
                    event_type=EVALUATION_LINEAGE_RECORDED
                )
            ],
            key=lambda record: (record.created_at, record.lineage_id),
        )

    def get_evidence(self, evidence_id: str) -> EvaluationEvidenceRecord:
        for evidence in self.list_evidence():
            if evidence.evidence_id == evidence_id:
                return evidence
        raise EvaluationEvidenceNotFoundError(
            f"Evaluation evidence not found: {evidence_id}"
        )

    def list_evidence(
        self,
        lineage_id: str | None = None,
    ) -> list[EvaluationEvidenceRecord]:
        records = sorted(
            [
                _evidence_from_event_metadata(event.metadata, event.ts)
                for event in self._events.list_persisted_events(
                    event_type=EVALUATION_LINEAGE_EVIDENCE_RECORDED
                )
            ],
            key=lambda evidence: (evidence.created_at, evidence.evidence_id),
        )
        if lineage_id is not None:
            records = [
                evidence
                for evidence in records
                if evidence.lineage_id == lineage_id
            ]
        return records

    def build_projection(
        self,
        *,
        metadata: ProjectionMetadata,
        generated_at: datetime,
    ) -> EvaluationLineageProjection:
        lineage_records = self.list_lineage()
        evidence_records = self.list_evidence()
        return EvaluationLineageProjection(
            metadata=metadata,
            lineage_records=lineage_records,
            evidence_records=evidence_records,
            total_lineage_records=len(lineage_records),
            total_evidence_records=len(evidence_records),
            generated_at=generated_at,
        )


def _lineage_from_event_metadata(
    metadata: dict,
    created_at: str,
) -> EvaluationLineageRecord:
    return EvaluationLineageRecord(
        lineage_id=str(metadata["lineage_id"]),
        evaluation_id=str(metadata["evaluation_id"]),
        evaluation_name=str(metadata["evaluation_name"]),
        evaluation_version=int(metadata["evaluation_version"]),
        source_type=str(metadata["source_type"]),
        source_id=str(metadata["source_id"]),
        source_category=str(metadata["source_category"]),
        created_at=datetime.fromisoformat(created_at),
    )


def _evidence_from_event_metadata(
    metadata: dict,
    created_at: str,
) -> EvaluationEvidenceRecord:
    return EvaluationEvidenceRecord(
        evidence_id=str(metadata["evidence_id"]),
        lineage_id=str(metadata["lineage_id"]),
        evidence_type=str(metadata["evidence_type"]),
        evidence_reference=str(metadata["evidence_reference"]),
        description=str(metadata["description"]),
        created_at=datetime.fromisoformat(created_at),
    )


evaluation_lineage_service = EvaluationLineageService()
