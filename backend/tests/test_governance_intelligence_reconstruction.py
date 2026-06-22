from datetime import UTC, datetime

from app.models.decision_record import DecisionType
from app.models.evaluation_record import EvaluationRecord, EvaluationRecordCreate
from app.models.planner import PlannerRequest, PlannerResponse
from app.models.tool import Tool
from app.services.decision_effectiveness_projection_builder_service import (
    DecisionEffectivenessProjectionBuilderService,
)
from app.services.decision_record_service import decision_record_service
from app.services.evaluation_outcome_rollup_projection_builder_service import (
    EvaluationOutcomeRollupProjectionBuilderService,
)
from app.services.evaluation_record_service import evaluation_record_service
from app.services.evaluation_summary_projection_builder_service import (
    EvaluationSummaryProjectionBuilderService,
)
from app.services.evaluation_trend_projection_v2_builder_service import (
    EvaluationTrendProjectionBuilderService,
)
from app.services.governance_health_rollup_projection_builder_service import (
    GovernanceHealthRollupProjectionBuilderService,
)
from app.services.planner_recommendation_service import (
    planner_recommendation_service,
)
from app.services.policy_evaluation_overview_projection_builder_service import (
    PolicyEvaluationOverviewProjectionBuilderService,
)
from app.services.policy_service import policy_service
from app.services.recommendation_outcome_projection_builder_service import (
    RecommendationOutcomeProjectionBuilderService,
)
from app.services.runtime_session_service import runtime_session_service


GENERATED_AT = datetime(2026, 6, 20, 15, 0, tzinfo=UTC)


def planner_tool(
    tool_id: str = "governance-intelligence-tool",
    name: str = "governance.intelligence",
) -> Tool:
    return Tool(
        id=tool_id,
        name=name,
        description="Governance intelligence reconstruction test tool",
        enabled=True,
        created_at="2026-06-20T00:00:00+00:00",
        updated_at="2026-06-20T00:00:00+00:00",
        parameters=[],
    )


def create_recommendation(
    *,
    session_id: str,
    task_id: str,
    objective: str,
    tool: Tool | None = None,
):
    return planner_recommendation_service.create_recommendation(
        PlannerRequest(
            task_id=task_id,
            session_id=session_id,
            objective=objective,
            available_tools=[planner_tool()],
        ),
        PlannerResponse(
            proposed_tool=tool or planner_tool(),
            rationale=f"Recommend {objective}",
            confidence=0.8,
        ),
        {"governance_status": "ok"},
    )


def create_decision(session_id: str, task_id: str, objective: str):
    recommendation = create_recommendation(
        session_id=session_id,
        task_id=task_id,
        objective=objective,
    )
    return decision_record_service.create_decision_record(
        session_id,
        DecisionType.RECOMMENDATION_SELECTION,
        recommendation.id,
        f"Select {objective}",
    )


def create_evaluation(
    *,
    target_type: str,
    target_id: str,
    outcome: str,
    score: float | None = None,
) -> str:
    record = evaluation_record_service.create_record(
        EvaluationRecordCreate(
            target_type=target_type,
            target_id=target_id,
            evaluation_type="outcome",
            outcome=outcome,
            score=score,
            evaluator="test-suite",
        )
    )
    return record.evaluation_id


def add_timed_evaluation(
    *,
    evaluation_id: str,
    target_type: str,
    target_id: str,
    outcome: str,
    created_at: datetime,
    score: float | None = None,
) -> None:
    record = EvaluationRecord.model_construct(
        session_id=None,
        task_id=None,
        target_type=target_type,
        target_id=target_id,
        evaluation_type="outcome",
        outcome=outcome,
        score=score,
        evaluator="test-suite",
        rationale=None,
        metadata={},
        evaluation_id=evaluation_id,
        created_at=created_at,
    )
    evaluation_record_service._records[record.evaluation_id] = record  # noqa: SLF001


def build_governance_intelligence() -> dict[str, object]:
    summary = EvaluationSummaryProjectionBuilderService(
        clock=lambda: GENERATED_AT
    )
    outcome = EvaluationOutcomeRollupProjectionBuilderService(
        clock=lambda: GENERATED_AT
    )
    trend = EvaluationTrendProjectionBuilderService(
        clock=lambda: GENERATED_AT
    )
    policy = PolicyEvaluationOverviewProjectionBuilderService(
        clock=lambda: GENERATED_AT
    )
    recommendation = RecommendationOutcomeProjectionBuilderService(
        clock=lambda: GENERATED_AT
    )
    decision = DecisionEffectivenessProjectionBuilderService(
        clock=lambda: GENERATED_AT
    )
    health = GovernanceHealthRollupProjectionBuilderService(
        recommendations=recommendation,
        decisions=decision,
        policies=policy,
        clock=lambda: GENERATED_AT,
    )

    return {
        "evaluation_summary": summary.build().model_dump(mode="json"),
        "evaluation_outcome_rollup": outcome.build().model_dump(mode="json"),
        "evaluation_trend": trend.build().model_dump(mode="json"),
        "policy_evaluation_overview": [
            projection.model_dump(mode="json")
            for projection in policy.build()
        ],
        "recommendation_outcome": [
            projection.model_dump(mode="json")
            for projection in recommendation.build()
        ],
        "decision_effectiveness": [
            projection.model_dump(mode="json")
            for projection in decision.build()
        ],
        "governance_health_rollup": health.build().model_dump(mode="json"),
    }


def source_snapshot() -> dict[str, object]:
    return {
        "evaluations": [
            record.model_dump(mode="json")
            for record in evaluation_record_service.list_records()
        ],
        "recommendations": [
            (
                record.id,
                record.task_id,
                record.session_id,
                record.status,
                record.governance_status,
                record.created_at.isoformat(),
            )
            for record in planner_recommendation_service.list_recommendations()
        ],
        "decisions": [
            (
                record.decision_id,
                record.session_id,
                record.task_id,
                record.decision_type,
                record.selected_entity_id,
                record.selected_entity_type,
                record.created_at.isoformat(),
            )
            for record in decision_record_service.list_decision_records()
        ],
        "policies": [
            (
                record.id,
                record.name,
                record.policy_type,
                record.status,
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
            )
            for record in policy_service.list_policies()
        ],
    }


def test_governance_intelligence_empty_state_rebuilds_are_stable() -> None:
    first = build_governance_intelligence()
    second = build_governance_intelligence()
    third = build_governance_intelligence()

    assert first == second
    assert second == third
    assert first["evaluation_summary"]["total_evaluations"] == 0
    assert first["evaluation_summary"]["evaluations_by_type"] == {}
    assert first["evaluation_summary"]["evaluations_by_outcome"] == {}
    assert first["evaluation_outcome_rollup"]["total_evaluations"] == 0
    assert first["evaluation_outcome_rollup"]["success_rate"] == 0.0
    assert first["evaluation_outcome_rollup"]["failure_rate"] == 0.0
    assert first["evaluation_trend"]["buckets"] == []
    assert first["policy_evaluation_overview"] == []
    assert first["recommendation_outcome"] == []
    assert first["decision_effectiveness"] == []
    assert first["governance_health_rollup"]["health_status"] == "unknown"
    assert first["governance_health_rollup"]["health_reasons"] == [
        "no_evaluation_data"
    ]


def test_governance_intelligence_rebuilds_are_deterministic_and_read_only() -> None:
    session = runtime_session_service.create_session(
        "governance-intelligence-reconstruction"
    )
    selected_recommendation = create_recommendation(
        session_id=session.id,
        task_id=session.task_id,
        objective="selected recommendation",
        tool=planner_tool("shell-read", "shell.read"),
    )
    not_selected_recommendation = create_recommendation(
        session_id=session.id,
        task_id=session.task_id,
        objective="not selected recommendation",
        tool=planner_tool("code-format", "code.format"),
    )
    first_decision = create_decision(
        session.id,
        session.task_id,
        "covered decision",
    )
    second_decision = create_decision(
        session.id,
        session.task_id,
        "uncovered decision",
    )
    policy = policy_service.create_policy(
        name="Alpha governance policy",
        description="Policy linked to evaluation evidence.",
        policy_type="governance",
        status="active",
    )
    empty_policy = policy_service.create_policy(
        name="Omega empty policy",
        description="Policy without linked evaluation evidence.",
        policy_type="governance",
        status="active",
    )
    policy_version = policy_service.add_policy_version(
        policy.id,
        version=1,
        rule_payload={"rule": "governance"},
    )

    decision_evaluation_id = create_evaluation(
        target_type="decision",
        target_id=first_decision.decision_id,
        outcome="success",
        score=0.9,
    )
    create_evaluation(
        target_type="decision",
        target_id=first_decision.decision_id,
        outcome="failure",
        score=0.3,
    )
    create_evaluation(
        target_type="recommendation",
        target_id=selected_recommendation.id,
        outcome="success",
        score=0.8,
    )
    create_evaluation(
        target_type="recommendation",
        target_id=not_selected_recommendation.id,
        outcome="rejected",
        score=0.2,
    )
    create_evaluation(
        target_type="artifact",
        target_id="artifact-1",
        outcome="accepted",
        score=0.7,
    )
    create_evaluation(
        target_type="decision",
        target_id="orphan-decision",
        outcome="success",
        score=1.0,
    )
    create_evaluation(
        target_type="recommendation",
        target_id="orphan-recommendation",
        outcome="success",
        score=1.0,
    )
    policy_service.record_policy_decision(
        policy.id,
        policy_version.id,
        target_type="decision",
        target_id=first_decision.decision_id,
        decision="allow",
        reason="Linked to decision evaluation.",
        evaluation_id=decision_evaluation_id,
    )

    before = source_snapshot()
    first = build_governance_intelligence()
    second = build_governance_intelligence()
    third = build_governance_intelligence()
    after = source_snapshot()

    assert first == second
    assert second == third
    assert before == after

    policy_projection = first["policy_evaluation_overview"]
    assert [
        projection["policy_id"]
        for projection in policy_projection
    ] == [policy.id, empty_policy.id]
    assert [
        projection["total_evaluations"]
        for projection in policy_projection
    ] == [1, 0]
    assert policy_projection[1]["average_score"] is None

    recommendation_projection = first["recommendation_outcome"]
    assert {
        projection["recommendation_id"]
        for projection in recommendation_projection
    } == {
        record.id
        for record in planner_recommendation_service.list_recommendations()
    }
    recommendation_sort_keys = [
        (
            -projection["selected_count"],
            -projection["success_rate"],
            projection["recommendation_category"],
            projection["recommendation_type"],
            projection["recommendation_id"],
        )
        for projection in recommendation_projection
    ]
    assert recommendation_sort_keys == sorted(recommendation_sort_keys)
    assert [
        projection["evaluation_count"]
        for projection in recommendation_projection
        if projection["recommendation_id"]
        in {selected_recommendation.id, not_selected_recommendation.id}
    ] == [1, 1]
    assert "orphan-recommendation" not in {
        projection["recommendation_id"]
        for projection in recommendation_projection
    }

    decision_projection = first["decision_effectiveness"]
    assert [
        projection["decision_id"]
        for projection in decision_projection
    ] == [
        first_decision.decision_id,
        second_decision.decision_id,
    ]
    assert [
        projection["has_evaluation_coverage"]
        for projection in decision_projection
    ] == [True, False]
    assert "orphan-decision" not in {
        projection["decision_id"]
        for projection in decision_projection
    }

    trend = first["evaluation_trend"]
    assert len(trend["buckets"]) == 1
    assert trend["buckets"][0]["total_evaluations"] == 7
    assert first["evaluation_outcome_rollup"]["total_evaluations"] == 7
    assert first["evaluation_outcome_rollup"]["success_rate"] == 4 / 7
    assert first["evaluation_outcome_rollup"]["failure_rate"] == 1 / 7
    assert first["evaluation_outcome_rollup"]["acceptance_rate"] == 1 / 7
    assert first["evaluation_outcome_rollup"]["rejection_rate"] == 1 / 7
    assert first["evaluation_summary"]["total_evaluations"] == 7
    assert first["governance_health_rollup"]["total_evaluations"] == 7
    assert first["governance_health_rollup"]["health_status"] == "degraded"
    assert first["governance_health_rollup"]["health_reasons"] == [
        "overall_success_rate_below_0.6"
    ]


def test_evaluation_trend_bucket_generation_and_ordering_are_deterministic() -> None:
    add_timed_evaluation(
        evaluation_id="evaluation-record-late",
        target_type="artifact",
        target_id="artifact-late",
        outcome="rejected",
        created_at=datetime(2026, 6, 20, 18, 0, tzinfo=UTC),
    )
    add_timed_evaluation(
        evaluation_id="evaluation-record-early-success",
        target_type="artifact",
        target_id="artifact-early-success",
        outcome="success",
        created_at=datetime(2026, 6, 18, 9, 0, tzinfo=UTC),
    )
    add_timed_evaluation(
        evaluation_id="evaluation-record-middle",
        target_type="artifact",
        target_id="artifact-middle",
        outcome="accepted",
        created_at=datetime(2026, 6, 19, 12, 0, tzinfo=UTC),
    )
    add_timed_evaluation(
        evaluation_id="evaluation-record-early-failure",
        target_type="artifact",
        target_id="artifact-early-failure",
        outcome="failure",
        created_at=datetime(2026, 6, 18, 16, 0, tzinfo=UTC),
    )

    before = source_snapshot()
    first = build_governance_intelligence()["evaluation_trend"]
    second = build_governance_intelligence()["evaluation_trend"]
    after = source_snapshot()

    assert first == second
    assert before == after
    assert [
        bucket["bucket_start"]
        for bucket in first["buckets"]
    ] == [
        "2026-06-18T00:00:00+00:00",
        "2026-06-19T00:00:00+00:00",
        "2026-06-20T00:00:00+00:00",
    ]
    assert [
        bucket["total_evaluations"]
        for bucket in first["buckets"]
    ] == [2, 1, 1]
    assert first["buckets"][0]["evaluations_by_outcome"] == {
        "failure": 1,
        "success": 1,
    }
