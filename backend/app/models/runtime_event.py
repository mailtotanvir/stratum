from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EventType(StrEnum):
    ASK_HUMAN_REQUESTED = "ask_human_requested"
    ASK_HUMAN_RESPONDED = "ask_human_responded"
    DEMO_TASK_COMPLETED = "demo_task_completed"
    RUNTIME_TASK_STARTED = "runtime_task_started"
    RUNTIME_TASK_INTERRUPTED = "runtime_task_interrupted"
    RUNTIME_TASK_STOPPED = "runtime_task_stopped"
    RUNTIME_GOVERNANCE_WARNING = "runtime_governance_warning"
    RUNTIME_GOVERNANCE_BLOCKED = "runtime_governance_blocked"
    REFLECTION_REQUESTED = "reflection_requested"
    REFLECTION_RESOLVED = "reflection_resolved"
    INTERRUPT_REQUESTED = "interrupt_requested"
    INTERRUPT_APPLIED = "interrupt_applied"
    INTERRUPT_IGNORED = "interrupt_ignored"
    STOP_REQUESTED = "stop_requested"
    STOP_APPLIED = "stop_applied"
    STOP_IGNORED = "stop_ignored"
    ARTIFACT_CREATED = "artifact_created"
    RUNTIME_ARTIFACT_ATTACHED = "runtime_artifact_attached"
    PROPOSAL_ARTIFACT_ATTACHED = "proposal_artifact_attached"
    RUNTIME_SESSION_CREATED = "runtime_session_created"
    RUNTIME_SESSION_RUNNING = "runtime_session_running"
    RUNTIME_SESSION_COMPLETED = "runtime_session_completed"
    RUNTIME_SESSION_INTERRUPTED = "runtime_session_interrupted"
    RUNTIME_SESSION_STOPPED = "runtime_session_stopped"
    TOOL_REGISTERED = "tool_registered"
    TOOL_ENABLED = "tool_enabled"
    TOOL_DISABLED = "tool_disabled"
    TOOL_INVOCATION_REQUESTED = "tool_invocation_requested"
    TOOL_INVOCATION_RUNNING = "tool_invocation_running"
    TOOL_INVOCATION_COMPLETED = "tool_invocation_completed"
    TOOL_INVOCATION_FAILED = "tool_invocation_failed"
    TOOL_EXECUTION_STARTED = "tool_execution_started"
    TOOL_EXECUTION_COMPLETED = "tool_execution_completed"
    TOOL_EXECUTION_FAILED = "tool_execution_failed"
    TOOL_EXECUTION_GOVERNANCE_WARNING = "tool_execution_governance_warning"
    TOOL_EXECUTION_GOVERNANCE_BLOCKED = "tool_execution_governance_blocked"
    PLANNER_INPUT_BUILT = "planner_input_built"
    PLANNER_REQUESTED = "planner_requested"
    PLANNER_COMPLETED = "planner_completed"
    PLANNER_PROPOSAL_CREATED = "planner_proposal_created"
    PLANNER_RECOMMENDATION_CREATED = "planner_recommendation_created"
    PLANNER_RECOMMENDATION_PROMOTED = "planner_recommendation_promoted"
    PLANNER_RECOMMENDATION_DISMISSED = "planner_recommendation_dismissed"
    DECISION_RECORD_CREATED = "decision_record_created"
    DECISION_EVIDENCE_CREATED = "decision_evidence_created"
    EVALUATION_CREATED = "evaluation_created"
    EVALUATION_RESULT_ADDED = "evaluation_result_added"
    EVALUATION_DEFINITION_REGISTERED = "evaluation_definition_registered"
    EVALUATION_SUITE_REGISTERED = "evaluation_suite_registered"
    EVALUATION_LINEAGE_RECORDED = "evaluation_lineage_recorded"
    EVALUATION_LINEAGE_EVIDENCE_RECORDED = (
        "evaluation_lineage_evidence_recorded"
    )
    EVALUATION_COVERAGE_TARGET_REGISTERED = (
        "evaluation_coverage_target_registered"
    )
    EVALUATION_COVERAGE_MAPPING_REGISTERED = (
        "evaluation_coverage_mapping_registered"
    )
    EVALUATION_DRIFT_BASELINE_REGISTERED = (
        "evaluation_drift_baseline_registered"
    )
    EVALUATION_DRIFT_OBSERVATION_REGISTERED = (
        "evaluation_drift_observation_registered"
    )
    POLICY_CREATED = "policy_created"
    POLICY_VERSION_ADDED = "policy_version_added"
    POLICY_DECISION_RECORDED = "policy_decision_recorded"
    POLICY_VIOLATION_RECORDED = "policy_violation_recorded"
    DECISION_PROJECTION_BUILT = "decision_projection_built"
    SESSION_DECISION_PROJECTION_BUILT = "session_decision_projection_built"
    PROJECTION_REGISTRY_INSPECTED = "projection_registry_inspected"
    PROJECTION_REBUILD_STARTED = "projection_rebuild_started"
    PROJECTION_REBUILD_COMPLETED = "projection_rebuild_completed"
    PROJECTION_REBUILD_FAILED = "projection_rebuild_failed"
    PROJECTION_REPLAY_STARTED = "projection_replay_started"
    PROJECTION_REPLAY_COMPLETED = "projection_replay_completed"
    PROJECTION_REPLAY_FAILED = "projection_replay_failed"
    PROJECTION_REPLAY_DRY_RUN_COMPLETED = (
        "projection_replay_dry_run_completed"
    )
    PROJECTION_DRIFT_CHECK_STARTED = "projection_drift_check_started"
    PROJECTION_DRIFT_CHECK_COMPLETED = "projection_drift_check_completed"
    PROJECTION_DRIFT_DETECTED = "projection_drift_detected"
    PROJECTION_DRIFT_CHECK_FAILED = "projection_drift_check_failed"
    GOVERNANCE_PROJECTION_UPDATED = "governance_projection_updated"
    GOVERNANCE_DECISION_RECORDED = "governance_decision_recorded"
    GOVERNANCE_PROJECTION_REBUILT = "governance_projection_rebuilt"
    DECISION_LINEAGE_UPDATED = "decision_lineage_updated"
    DECISION_LINEAGE_REBUILT = "decision_lineage_rebuilt"
    DECISION_LINEAGE_INCOMPLETE = "decision_lineage_incomplete"
    DECISION_LINEAGE_RECONSTRUCTION_FAILED = (
        "decision_lineage_reconstruction_failed"
    )
    ARTIFACT_LINEAGE_UPDATED = "artifact_lineage_updated"
    ARTIFACT_LINEAGE_REBUILT = "artifact_lineage_rebuilt"
    ARTIFACT_LINEAGE_INCOMPLETE = "artifact_lineage_incomplete"
    ARTIFACT_LINEAGE_RECONSTRUCTION_FAILED = (
        "artifact_lineage_reconstruction_failed"
    )
    PROJECTION_VERIFICATION_STARTED = "projection_verification_started"
    PROJECTION_VERIFICATION_COMPLETED = "projection_verification_completed"
    PROJECTION_VERIFICATION_FAILED = "projection_verification_failed"
    PROJECTION_MANIFEST_GENERATED = "projection_manifest_generated"
    PROJECTION_MANIFEST_HASH_COMPUTED = "projection_manifest_hash_computed"
    PROJECTION_MANIFEST_GENERATION_FAILED = (
        "projection_manifest_generation_failed"
    )
    PROJECTION_SNAPSHOT_EXPORT_STARTED = "projection_snapshot_export_started"
    PROJECTION_SNAPSHOT_EXPORT_COMPLETED = (
        "projection_snapshot_export_completed"
    )
    PROJECTION_SNAPSHOT_EXPORT_FAILED = "projection_snapshot_export_failed"
    PROJECTION_LINEAGE_GENERATED = "projection_lineage_generated"
    PROJECTION_LINEAGE_GENERATION_FAILED = (
        "projection_lineage_generation_failed"
    )
    RUNTIME_QUERY_REGISTERED = "runtime_query_registered"
    RUNTIME_QUERY_DISCOVERED = "runtime_query_discovered"
    RUNTIME_QUERY_EXECUTED = "runtime_query_executed"
    RUNTIME_QUERY_EXECUTION_STARTED = "runtime_query_execution_started"
    RUNTIME_QUERY_EXECUTION_COMPLETED = "runtime_query_execution_completed"
    RUNTIME_QUERY_EXECUTION_FAILED = "runtime_query_execution_failed"
    QUERY_HISTORY_RECORDED = "query_history_recorded"
    QUERY_HISTORY_RETRIEVED = "query_history_retrieved"
    QUERY_RECONSTRUCTION_GENERATED = "query_reconstruction_generated"
    QUERY_VERIFICATION_STARTED = "query_verification_started"
    QUERY_VERIFICATION_COMPLETED = "query_verification_completed"
    QUERY_VERIFICATION_FAILED = "query_verification_failed"
    QUERY_LINEAGE_GENERATED = "query_lineage_generated"
    QUERY_LINEAGE_GENERATION_FAILED = "query_lineage_generation_failed"
    QUERY_MANIFEST_GENERATED = "query_manifest_generated"
    QUERY_MANIFEST_HASH_COMPUTED = "query_manifest_hash_computed"
    QUERY_MANIFEST_GENERATION_FAILED = "query_manifest_generation_failed"
    QUERY_SNAPSHOT_EXPORT_STARTED = "query_snapshot_export_started"
    QUERY_SNAPSHOT_EXPORT_COMPLETED = "query_snapshot_export_completed"
    QUERY_SNAPSHOT_EXPORT_FAILED = "query_snapshot_export_failed"
    RUNTIME_DASHBOARD_GENERATED = "runtime_dashboard_generated"
    RUNTIME_DASHBOARD_GENERATION_FAILED = (
        "runtime_dashboard_generation_failed"
    )
    RUNTIME_HEALTH_EVALUATED = "runtime_health_evaluated"
    RUNTIME_HEALTH_SUBSYSTEM_EVALUATED = (
        "runtime_health_subsystem_evaluated"
    )
    RUNTIME_HEALTH_CHECK_FAILED = "runtime_health_check_failed"
    RUNTIME_RECONSTRUCTION_VIEW_BUILT = (
        "runtime_reconstruction_view_built"
    )
    RUNTIME_RECONSTRUCTION_VIEW_INCOMPLETE = (
        "runtime_reconstruction_view_incomplete"
    )
    RUNTIME_RECONSTRUCTION_VIEW_FAILED = (
        "runtime_reconstruction_view_failed"
    )
    OPERATIONAL_ANALYTICS_GENERATED = "operational_analytics_generated"
    OPERATIONAL_ANALYTICS_FAILED = "operational_analytics_failed"
    RUNTIME_INTELLIGENCE_GENERATED = "runtime_intelligence_generated"
    RUNTIME_INTELLIGENCE_FAILED = "runtime_intelligence_failed"
    RUNTIME_RISK_DETECTED = "runtime_risk_detected"
    EXPLANATION_GENERATED = "explanation_generated"
    EXPLANATION_INCOMPLETE = "explanation_incomplete"
    EXPLANATION_FAILED = "explanation_failed"
    PROJECTION_REGISTERED = "projection_registered"
    PROJECTION_REGISTRATION_FAILED = "projection_registration_failed"
    PROJECTION_CONTRACT_VALIDATED = "projection_contract_validated"
    PROJECTION_CONTRACT_INVALID = "projection_contract_invalid"
    PROVIDER_OBSERVABILITY_GENERATED = "provider_observability_generated"
    PROVIDER_OBSERVABILITY_FAILED = "provider_observability_failed"
    PROVIDER_COST_ESTIMATE_GENERATED = "provider_cost_estimate_generated"
    PROVIDER_EXECUTION_REQUESTED = "provider_execution_requested"
    PROVIDER_EXECUTION_VALIDATION_FAILED = (
        "provider_execution_validation_failed"
    )
    PROVIDER_EXECUTION_STARTED = "provider_execution_started"
    PROVIDER_EXECUTION_COMPLETED = "provider_execution_completed"
    PROVIDER_EXECUTION_FAILED = "provider_execution_failed"
    PROVIDER_EXECUTION_CANCELLED = "provider_execution_cancelled"
    PROVIDER_EXECUTION_STREAM_STARTED = (
        "provider_execution_stream_started"
    )
    PROVIDER_EXECUTION_STREAM_DELTA = "provider_execution_stream_delta"
    PROVIDER_EXECUTION_STREAM_COMPLETED = (
        "provider_execution_stream_completed"
    )
    PROVIDER_EXECUTION_STREAM_FAILED = "provider_execution_stream_failed"
    AGENT_EXECUTION_REQUESTED = "agent_execution_requested"
    AGENT_EXECUTION_STARTED = "agent_execution_started"
    AGENT_EXECUTION_COMPLETED = "agent_execution_completed"
    AGENT_EXECUTION_FAILED = "agent_execution_failed"
    AGENT_LOOP_STARTED = "agent_loop_started"
    AGENT_LOOP_PROVIDER_REQUESTED = "agent_loop_provider_requested"
    AGENT_LOOP_PROVIDER_COMPLETED = "agent_loop_provider_completed"
    AGENT_LOOP_TOOL_SELECTED = "agent_loop_tool_selected"
    AGENT_LOOP_TOOL_COMPLETED = "agent_loop_tool_completed"
    AGENT_LOOP_COMPLETED = "agent_loop_completed"
    AGENT_LOOP_FAILED = "agent_loop_failed"
    AGENT_LOOP_STOP_REQUESTED = "agent_loop_stop_requested"
    AGENT_LOOP_STOPPED = "agent_loop_stopped"
    WORK_LOOP_STARTED = "work_loop_started"
    WORK_LOOP_COMPLETED = "work_loop_completed"
    WORK_LOOP_FAILED = "work_loop_failed"
    TASK_CREATED = "task_created"
    TASK_RUNNING = "task_running"
    TASK_FAILED = "task_failed"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    PROPOSAL_GENERATED = "proposal_generated"
    PROPOSAL_RESOLVED = "proposal_resolved"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    WARNING = "warning"
    ERROR = "error"


class RuntimeEvent(BaseModel):
    id: int
    ts: str
    type: EventType
    severity: Severity = Severity.INFO
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("severity", mode="before")
    @classmethod
    def default_severity(cls, value: Any) -> Any:
        return Severity.INFO if value is None else value

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
