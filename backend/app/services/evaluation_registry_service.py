from datetime import datetime

from app.models.evaluation_registry import (
    EvaluationDefinition,
    EvaluationDefinitionCreate,
    EvaluationRegistryProjection,
    EvaluationSuite,
    EvaluationSuiteCreate,
)
from app.models.projection import ProjectionMetadata
from app.services.event_service import EventService, event_service


EVALUATION_DEFINITION_REGISTERED = "evaluation_definition_registered"
EVALUATION_SUITE_REGISTERED = "evaluation_suite_registered"


class EvaluationDefinitionAlreadyExistsError(ValueError):
    pass


class EvaluationDefinitionNotFoundError(LookupError):
    pass


class EvaluationSuiteAlreadyExistsError(ValueError):
    pass


class EvaluationSuiteNotFoundError(LookupError):
    pass


class EvaluationRegistryService:
    def __init__(
        self,
        events: EventService | None = None,
    ) -> None:
        self._events = events or event_service

    def register_definition(
        self,
        request: EvaluationDefinitionCreate,
    ) -> EvaluationDefinition:
        definitions = self.list_definitions()
        evaluation_id = (
            request.evaluation_id
            or f"evaluation-definition-{len(definitions) + 1}"
        )
        if evaluation_id in {
            definition.evaluation_id
            for definition in definitions
        }:
            raise EvaluationDefinitionAlreadyExistsError(
                f"Evaluation definition already registered: {evaluation_id}"
            )

        event = self._events.emit_event_sync(
            event_type=EVALUATION_DEFINITION_REGISTERED,
            message="Evaluation definition registered",
            metadata={
                **request.model_dump(exclude={"evaluation_id"}),
                "evaluation_id": evaluation_id,
            },
        )
        return _definition_from_event_metadata(event.metadata, event.ts)

    def register_suite(
        self,
        request: EvaluationSuiteCreate,
    ) -> EvaluationSuite:
        suites = self.list_suites()
        suite_id = request.suite_id or f"evaluation-suite-{len(suites) + 1}"
        if suite_id in {suite.suite_id for suite in suites}:
            raise EvaluationSuiteAlreadyExistsError(
                f"Evaluation suite already registered: {suite_id}"
            )

        definition_ids = {
            definition.evaluation_id
            for definition in self.list_definitions()
        }
        missing_ids = [
            evaluation_id
            for evaluation_id in request.evaluation_ids
            if evaluation_id not in definition_ids
        ]
        if missing_ids:
            raise EvaluationDefinitionNotFoundError(
                "Evaluation definition not found: "
                + ", ".join(sorted(missing_ids))
            )

        event = self._events.emit_event_sync(
            event_type=EVALUATION_SUITE_REGISTERED,
            message="Evaluation suite registered",
            metadata={
                **request.model_dump(exclude={"suite_id"}),
                "suite_id": suite_id,
            },
        )
        return _suite_from_event_metadata(event.metadata, event.ts)

    def get_definition(self, evaluation_id: str) -> EvaluationDefinition:
        for definition in self.list_definitions():
            if definition.evaluation_id == evaluation_id:
                return definition
        raise EvaluationDefinitionNotFoundError(
            f"Evaluation definition not found: {evaluation_id}"
        )

    def list_definitions(self) -> list[EvaluationDefinition]:
        return sorted(
            [
                _definition_from_event_metadata(event.metadata, event.ts)
                for event in self._events.list_persisted_events(
                    event_type=EVALUATION_DEFINITION_REGISTERED
                )
            ],
            key=lambda definition: (
                definition.created_at,
                definition.evaluation_id,
            ),
        )

    def get_suite(self, suite_id: str) -> EvaluationSuite:
        for suite in self.list_suites():
            if suite.suite_id == suite_id:
                return suite
        raise EvaluationSuiteNotFoundError(
            f"Evaluation suite not found: {suite_id}"
        )

    def list_suites(self) -> list[EvaluationSuite]:
        return sorted(
            [
                _suite_from_event_metadata(event.metadata, event.ts)
                for event in self._events.list_persisted_events(
                    event_type=EVALUATION_SUITE_REGISTERED
                )
            ],
            key=lambda suite: (suite.created_at, suite.suite_id),
        )

    def build_projection(
        self,
        *,
        metadata: ProjectionMetadata,
        generated_at: datetime,
    ) -> EvaluationRegistryProjection:
        definitions = self.list_definitions()
        suites = self.list_suites()
        return EvaluationRegistryProjection(
            metadata=metadata,
            definitions=definitions,
            suites=suites,
            total_definitions=len(definitions),
            total_suites=len(suites),
            generated_at=generated_at,
        )


def _definition_from_event_metadata(
    metadata: dict,
    created_at: str,
) -> EvaluationDefinition:
    return EvaluationDefinition(
        evaluation_id=str(metadata["evaluation_id"]),
        name=str(metadata["name"]),
        description=str(metadata["description"]),
        category=str(metadata["category"]),
        version=int(metadata["version"]),
        status=metadata["status"],
        created_at=datetime.fromisoformat(created_at),
    )


def _suite_from_event_metadata(
    metadata: dict,
    created_at: str,
) -> EvaluationSuite:
    return EvaluationSuite(
        suite_id=str(metadata["suite_id"]),
        name=str(metadata["name"]),
        description=str(metadata["description"]),
        evaluation_ids=list(metadata.get("evaluation_ids", [])),
        created_at=datetime.fromisoformat(created_at),
    )


evaluation_registry_service = EvaluationRegistryService()
