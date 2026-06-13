from copy import deepcopy
from datetime import datetime
from typing import Any

from app.models.query_execution_record import (
    QueryExecutionRecord,
    QueryHistoryDetailResponse,
    QueryHistoryMetadata,
    QueryHistoryResponse,
    QueryReconstructionInfo,
)
from app.models.runtime_event import EventType
from app.models.runtime_query_execution import RuntimeQueryExecutionMetadata
from app.services.event_service import EventService, event_service


RECONSTRUCTION_VERSION = 1


class QueryExecutionRecordNotFoundError(LookupError):
    pass


class QueryHistoryService:
    def __init__(self, events: EventService | None = None) -> None:
        self._events = events or event_service

    def record_execution(
        self,
        *,
        execution_id: str,
        executed_at: datetime,
        parameters: dict[str, Any],
        execution_metadata: RuntimeQueryExecutionMetadata,
        success: bool,
        result_summary: Any,
    ) -> QueryExecutionRecord:
        record = QueryExecutionRecord(
            execution_id=execution_id,
            query_name=execution_metadata.query_name,
            query_version=execution_metadata.query_version,
            executed_at=executed_at,
            parameters=deepcopy(parameters),
            execution_metadata=execution_metadata.model_copy(deep=True),
            success=success,
            result_summary=deepcopy(result_summary),
            lineage_reference={
                "execution_id": execution_id,
                "endpoint": f"/queries/history/{execution_id}/lineage",
            },
        )
        reconstruction = self.generate_reconstruction_info(
            record,
            emit_diagnostic=False,
        )
        self._events.emit_event_sync(
            event_type=EventType.QUERY_HISTORY_RECORDED,
            message=f"Query history recorded: {record.query_name}",
            metadata={
                **self._diagnostic_metadata(record),
                "execution_record": record.model_dump(mode="json"),
                "reconstruction_info": reconstruction.model_dump(mode="json"),
            },
        )
        self._emit_reconstruction_generated(record)
        return record

    def retrieve_history(self) -> QueryHistoryResponse:
        records = self._records()
        reconstruction_information = [
            self.generate_reconstruction_info(record)
            for record in records
        ]
        for record in records:
            self._emit_retrieved(record)
        return QueryHistoryResponse(
            execution_records=records,
            metadata=QueryHistoryMetadata(
                record_count=len(records),
                reconstruction_version=RECONSTRUCTION_VERSION,
            ),
            reconstruction_information=reconstruction_information,
        )

    def retrieve_execution(
        self,
        execution_id: str,
    ) -> QueryHistoryDetailResponse:
        record = self.load_execution_record(execution_id)
        reconstruction = self.generate_reconstruction_info(record)
        self._emit_retrieved(record)
        return QueryHistoryDetailResponse(
            execution_record=record,
            reconstruction_info=reconstruction,
        )

    def load_execution_snapshot(
        self,
        execution_id: str,
    ) -> tuple[QueryExecutionRecord, dict[str, Any]]:
        event = next(
            (
                candidate
                for candidate in self._events.list_persisted_events(
                    event_type=EventType.QUERY_HISTORY_RECORDED.value
                )
                if candidate.metadata.get("execution_id") == execution_id
            ),
            None,
        )
        if event is None:
            raise QueryExecutionRecordNotFoundError(
                f"Query execution record not found: {execution_id}"
            )
        return (
            QueryExecutionRecord.model_validate(
                event.metadata["execution_record"]
            ),
            deepcopy(event.metadata.get("reconstruction_info", {})),
        )

    def load_execution_record(
        self,
        execution_id: str,
    ) -> QueryExecutionRecord:
        record, _ = self.load_execution_snapshot(execution_id)
        return record

    def generate_reconstruction_info(
        self,
        record: QueryExecutionRecord,
        *,
        emit_diagnostic: bool = True,
    ) -> QueryReconstructionInfo:
        reconstruction = QueryReconstructionInfo(
            query_name=record.query_name,
            query_version=record.query_version,
            handler_name=record.execution_metadata.handler_name,
            execution_timestamp=record.executed_at,
            parameter_snapshot=deepcopy(record.parameters),
            reconstruction_version=RECONSTRUCTION_VERSION,
        )
        if emit_diagnostic:
            self._emit_reconstruction_generated(record)
        return reconstruction

    def _records(self) -> list[QueryExecutionRecord]:
        return [
            QueryExecutionRecord.model_validate(
                event.metadata["execution_record"]
            )
            for event in self._events.list_persisted_events(
                event_type=EventType.QUERY_HISTORY_RECORDED.value
            )
        ]

    def _emit_retrieved(self, record: QueryExecutionRecord) -> None:
        self._events.emit_event_sync(
            event_type=EventType.QUERY_HISTORY_RETRIEVED,
            message=f"Query history retrieved: {record.query_name}",
            metadata=self._diagnostic_metadata(record),
        )

    def _emit_reconstruction_generated(
        self,
        record: QueryExecutionRecord,
    ) -> None:
        self._events.emit_event_sync(
            event_type=EventType.QUERY_RECONSTRUCTION_GENERATED,
            message=f"Query reconstruction generated: {record.query_name}",
            metadata=self._diagnostic_metadata(record),
        )

    @staticmethod
    def _diagnostic_metadata(
        record: QueryExecutionRecord,
    ) -> dict[str, str | int]:
        return {
            "execution_id": record.execution_id,
            "query_name": record.query_name,
            "query_version": record.query_version,
        }


query_history_service = QueryHistoryService()
