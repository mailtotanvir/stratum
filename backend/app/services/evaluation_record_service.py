from datetime import UTC, datetime

from app.models.evaluation_record import (
    EvaluationOutcome,
    EvaluationRecord,
    EvaluationRecordCreate,
    EvaluationTargetType,
)


class EvaluationRecordNotFoundError(LookupError):
    pass


class EvaluationRecordService:
    def __init__(self) -> None:
        self._records: dict[str, EvaluationRecord] = {}
        self._sequence = 0

    def reset(self) -> None:
        self._records = {}
        self._sequence = 0

    def create_record(
        self,
        request: EvaluationRecordCreate,
    ) -> EvaluationRecord:
        self._sequence += 1
        record = EvaluationRecord(
            **request.model_dump(),
            evaluation_id=f"evaluation-record-{self._sequence}",
            created_at=datetime.now(UTC),
        )
        self._records[record.evaluation_id] = record
        return record.model_copy(deep=True)

    def get_record(
        self,
        evaluation_id: str,
    ) -> EvaluationRecord:
        try:
            return self._records[evaluation_id].model_copy(deep=True)
        except KeyError as exc:
            raise EvaluationRecordNotFoundError(
                f"Evaluation record not found: {evaluation_id}"
            ) from exc

    def list_records(
        self,
        target_type: EvaluationTargetType | None = None,
        target_id: str | None = None,
        evaluation_type: str | None = None,
        outcome: EvaluationOutcome | None = None,
    ) -> list[EvaluationRecord]:
        records = sorted(
            self._records.values(),
            key=lambda record: (record.created_at, record.evaluation_id),
        )
        if target_type is not None:
            records = [
                record
                for record in records
                if record.target_type == target_type
            ]
        if target_id is not None:
            records = [
                record
                for record in records
                if record.target_id == target_id
            ]
        if evaluation_type is not None:
            records = [
                record
                for record in records
                if record.evaluation_type == evaluation_type
            ]
        if outcome is not None:
            records = [
                record
                for record in records
                if record.outcome == outcome
            ]
        return [record.model_copy(deep=True) for record in records]


evaluation_record_service = EvaluationRecordService()
