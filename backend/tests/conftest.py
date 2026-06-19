import pytest

from app.services.artifact_service import artifact_service
from app.services.decision_evidence_service import decision_evidence_service
from app.services.decision_record_service import decision_record_service
from app.services.event_service import event_service
from app.services.evaluation_service import evaluation_service
from app.services.interrupt_service import interrupt_service
from app.services.planner_recommendation_service import planner_recommendation_service
from app.services.policy_service import policy_service
from app.services.proposal_service import proposal_service
from app.services.proposal_artifact_service import proposal_artifact_service
from app.services.reflection_service import reflection_service
from app.services.runtime_artifact_service import runtime_artifact_service
from app.services.runtime_execution_service import runtime_execution_service
from app.services.runtime_session_service import runtime_session_service
from app.services.stop_service import stop_service
from app.services.tool_registry_service import tool_registry_service
from app.services.tool_invocation_service import tool_invocation_service
from app.services.trace_service import TraceService


@pytest.fixture(autouse=True)
def use_temp_trace_store(tmp_path):
    artifact_service.set_db_path(tmp_path / "artifacts.db")
    decision_evidence_service.set_db_path(tmp_path / "decision_evidence.db")
    decision_record_service.set_db_path(tmp_path / "decision_records.db")
    event_service.set_trace_store(TraceService(tmp_path / "stratum.db"))
    evaluation_service.set_db_path(tmp_path / "evaluations.db")
    interrupt_service.set_db_path(tmp_path / "interrupts.db")
    planner_recommendation_service.set_db_path(tmp_path / "planner_recommendations.db")
    policy_service.set_db_path(tmp_path / "policies.db")
    proposal_service.set_db_path(tmp_path / "proposals.db")
    proposal_artifact_service.set_db_path(tmp_path / "proposal_artifacts.db")
    reflection_service.set_db_path(tmp_path / "reflections.db")
    runtime_artifact_service.set_db_path(tmp_path / "runtime_artifacts.db")
    runtime_execution_service.set_db_path(tmp_path / "runtime.db")
    runtime_session_service.set_db_path(tmp_path / "runtime_sessions.db")
    stop_service.set_db_path(tmp_path / "stops.db")
    tool_invocation_service.set_db_path(tmp_path / "tool_invocations.db")
    tool_registry_service.set_db_path(tmp_path / "tools.db")
