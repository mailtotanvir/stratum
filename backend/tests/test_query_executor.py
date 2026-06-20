from fastapi.testclient import TestClient

from app.main import app
from app.models.query_executor import QueryExecutionRequest
from app.services.query_catalog_service import QueryCatalogService
from app.services.query_executor_service import (
    QueryExecutionError,
    QueryExecutionNotFoundError,
    QueryExecutorService,
)


class RecordingEvaluationService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object | None]] = []

    def build(self, filters):
        self.calls.append(filters)
        return {"surface": "evaluation_summary", "filters": filters}


class RecordingOutcomeService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object | None]] = []

    def build(self, filters):
        self.calls.append(filters)
        return {"surface": "evaluation_outcome_rollup", "filters": filters}


class RecordingTrendService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object | None]] = []

    def build(self, filters):
        self.calls.append(filters)
        return {"surface": "evaluation_trend", "filters": filters}


class RecordingPolicyService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def list_policy_summaries(self, **filters):
        self.calls.append(filters)
        return [{"surface": "policy_summary"}]


class RecordingPolicyEvidenceService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def list_policy_evidence(self, **filters):
        self.calls.append(filters)
        return [{"surface": "policy_evidence"}]


class RecordingPolicyEvaluationOverviewService:
    def __init__(self) -> None:
        self.calls = 0

    def get_policy_evaluation_overview(self):
        self.calls += 1
        return {"surface": "policy_evaluation_overview"}


def service_with_recorders():
    evaluation = RecordingEvaluationService()
    outcome = RecordingOutcomeService()
    trend = RecordingTrendService()
    policy = RecordingPolicyService()
    evidence = RecordingPolicyEvidenceService()
    overview = RecordingPolicyEvaluationOverviewService()
    service = QueryExecutorService(
        catalog_service=QueryCatalogService(),
        evaluation_service=evaluation,
        evaluation_outcome_service=outcome,
        evaluation_trend_service=trend,
        policy_service=policy,
        policy_evidence_service=evidence,
        policy_evaluation_overview_service=overview,
    )
    return service, evaluation, outcome, trend, policy, evidence, overview


def test_valid_query_dispatch() -> None:
    service, evaluation, *_ = service_with_recorders()

    result = service.execute(
        QueryExecutionRequest(
            query_id="evaluation_summary",
            filters={"outcome": "success"},
        )
    )

    assert result.query_id == "runtime.evaluation_summary"
    assert result.projection_type == "evaluation_summary"
    assert result.route == "/runtime/evaluation-summary"
    assert result.result == {
        "surface": "evaluation_summary",
        "filters": {
            "target_type": None,
            "target_id": None,
            "evaluation_type": None,
            "outcome": "success",
        },
    }
    assert evaluation.calls == [
        {
            "target_type": None,
            "target_id": None,
            "evaluation_type": None,
            "outcome": "success",
        }
    ]


def test_invalid_query_id_rejection() -> None:
    service, *_ = service_with_recorders()

    try:
        service.execute(
            QueryExecutionRequest(
                query_id="missing_query",
                filters={},
            )
        )
    except QueryExecutionNotFoundError as exc:
        assert str(exc) == "Query catalog entry not found: missing_query"
    else:
        raise AssertionError("missing query_id should be rejected")


def test_catalog_valid_but_unsupported_query_is_rejected() -> None:
    service, *_ = service_with_recorders()

    try:
        service.execute(
            QueryExecutionRequest(
                query_id="decision_projection",
                filters={},
            )
        )
    except QueryExecutionError as exc:
        assert "Query execution is not supported" in str(exc)
    else:
        raise AssertionError("unsupported query_id should be rejected")


def test_filters_forwarded_correctly() -> None:
    service, _, _, trend, *_ = service_with_recorders()

    service.execute(
        QueryExecutionRequest(
            query_id="runtime.evaluation_trend",
            filters={
                "granularity": "day",
            },
        )
    )

    assert trend.calls == [
        {
            "granularity": "day",
        }
    ]


def test_supported_projections_execute_correctly() -> None:
    service, _, outcome, trend, policy, evidence, overview = (
        service_with_recorders()
    )

    assert service.execute(
        QueryExecutionRequest(query_id="evaluation_outcome_rollup")
    ).result == {
        "surface": "evaluation_outcome_rollup",
        "filters": {
            "target_type": None,
            "target_id": None,
            "evaluation_type": None,
            "outcome": None,
        },
    }
    assert service.execute(
        QueryExecutionRequest(query_id="evaluation_trend")
    ).result == {
        "surface": "evaluation_trend",
        "filters": {"granularity": None},
    }
    assert service.execute(
        QueryExecutionRequest(query_id="policy_summary")
    ).result == [{"surface": "policy_summary"}]
    assert service.execute(
        QueryExecutionRequest(query_id="policy_evidence")
    ).result == [{"surface": "policy_evidence"}]
    assert service.execute(
        QueryExecutionRequest(query_id="policy_evaluation_overview")
    ).result == {"surface": "policy_evaluation_overview"}

    assert len(outcome.calls) == 1
    assert len(trend.calls) == 1
    assert len(policy.calls) == 1
    assert len(evidence.calls) == 1
    assert overview.calls == 1


def test_execution_result_metadata_populated() -> None:
    service, *_ = service_with_recorders()

    result = service.execute(
        QueryExecutionRequest(query_id="policy_evidence")
    )

    assert result.query_id == "runtime.policy_evidence"
    assert result.projection_type == "policy_evidence"
    assert result.route == "/runtime/policy-evidence"
    assert result.executed_at is not None


def test_policy_evaluation_overview_execution_metadata() -> None:
    service, *_, overview = service_with_recorders()

    result = service.execute(
        QueryExecutionRequest(query_id="policy_evaluation_overview")
    )

    assert result.query_id == "runtime.policy_evaluation_overview"
    assert result.projection_type == "policy_evaluation_overview"
    assert result.route == "/runtime/policy-evaluation-overview"
    assert result.result == {"surface": "policy_evaluation_overview"}
    assert result.executed_at is not None
    assert overview.calls == 1


def test_query_executor_route_works() -> None:
    response = TestClient(app).post(
        "/runtime/query-execute",
        json={"query_id": "evaluation_summary", "filters": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query_id"] == "runtime.evaluation_summary"
    assert body["projection_type"] == "evaluation_summary"
    assert body["route"] == "/runtime/evaluation-summary"
    assert "executed_at" in body
    assert "result" in body


def test_query_executor_route_rejects_invalid_query_id() -> None:
    response = TestClient(app).post(
        "/runtime/query-execute",
        json={"query_id": "missing_query", "filters": {}},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Query catalog entry not found: missing_query"
    }
