from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RuntimeEventRecord(Base):
    __tablename__ = "runtime_events"

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(Integer, index=True)
    ts: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text, index=True)
    severity: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text)


class TaskRecord(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text)


class RuntimeExecutionRecord(Base):
    __tablename__ = "runtime_executions"

    task_id: Mapped[str] = mapped_column(Text, primary_key=True)
    state: Mapped[str] = mapped_column(Text, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interrupted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ReflectionRequestRecord(Base):
    __tablename__ = "reflection_requests"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str] = mapped_column(Text, index=True)
    status: Mapped[str] = mapped_column(Text, index=True)
    reasons_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InterruptRequestRecord(Base):
    __tablename__ = "interrupt_requests"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str] = mapped_column(Text, index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StopRequestRecord(Base):
    __tablename__ = "stop_requests"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str] = mapped_column(Text, index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ArtifactRecord(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str | None] = mapped_column(Text, index=True)
    proposal_id: Mapped[str | None] = mapped_column(Text, index=True)
    path: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text)


class RuntimeArtifactLinkRecord(Base):
    __tablename__ = "runtime_artifact_links"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str] = mapped_column(Text, index=True)
    session_id: Mapped[str | None] = mapped_column(Text, index=True)
    artifact_id: Mapped[str] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ProposalArtifactLinkRecord(Base):
    __tablename__ = "proposal_artifact_links"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    proposal_id: Mapped[str] = mapped_column(Text, index=True)
    artifact_id: Mapped[str] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RuntimeSessionRecord(Base):
    __tablename__ = "runtime_sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str] = mapped_column(Text, index=True)
    status: Mapped[str] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ToolRecord(Base):
    __tablename__ = "tools"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ToolParameterRecord(Base):
    __tablename__ = "tool_parameters"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    tool_id: Mapped[str] = mapped_column(Text, index=True)
    name: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)
    required: Mapped[bool] = mapped_column(Boolean)


class ToolInvocationRecord(Base):
    __tablename__ = "tool_invocations"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(Text, index=True)
    tool_id: Mapped[str] = mapped_column(Text, index=True)
    status: Mapped[str] = mapped_column(Text, index=True)
    input_payload_json: Mapped[str | None] = mapped_column(Text)
    output_payload_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlannerRecommendationRecord(Base):
    __tablename__ = "planner_recommendations"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str] = mapped_column(Text, index=True)
    session_id: Mapped[str] = mapped_column(Text, index=True)
    objective: Mapped[str] = mapped_column(Text)
    proposed_tool_json: Mapped[str | None] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    governance_status: Mapped[str] = mapped_column(Text, index=True)
    status: Mapped[str] = mapped_column(Text, index=True)
    context_snapshot_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class DecisionRecordRecord(Base):
    __tablename__ = "decision_records"

    decision_id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(Text, index=True)
    task_id: Mapped[str] = mapped_column(Text, index=True)
    decision_type: Mapped[str] = mapped_column(Text, index=True)
    selected_entity_id: Mapped[str] = mapped_column(Text, index=True)
    selected_entity_type: Mapped[str] = mapped_column(Text, index=True)
    rationale: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class DecisionEvidenceRecord(Base):
    __tablename__ = "decision_evidence"

    evidence_id: Mapped[str] = mapped_column(Text, primary_key=True)
    decision_id: Mapped[str] = mapped_column(Text, index=True)
    evidence_type: Mapped[str] = mapped_column(Text, index=True)
    evidence_reference: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class EvaluationDimensionRecord(Base):
    __tablename__ = "evaluation_dimensions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, index=True)
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class EvaluationRecord(Base):
    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str | None] = mapped_column(Text, index=True)
    decision_id: Mapped[str | None] = mapped_column(Text, index=True)
    artifact_id: Mapped[str | None] = mapped_column(Text, index=True)
    evaluation_type: Mapped[str] = mapped_column(Text, index=True)
    status: Mapped[str] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class EvaluationResultRecord(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(Text, index=True)
    dimension_id: Mapped[str] = mapped_column(Text, index=True)
    score: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class EvaluationTargetSnapshotRecord(Base):
    __tablename__ = "evaluation_target_snapshots"

    evaluation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    target_type: Mapped[str] = mapped_column(Text, index=True)
    target_id: Mapped[str] = mapped_column(Text, index=True)
    target_summary: Mapped[str] = mapped_column(Text)
    target_metadata_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ProposalRecord(Base):
    __tablename__ = "proposals"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str | None] = mapped_column(Text, index=True)
    source_type: Mapped[str] = mapped_column(Text, index=True)
    source_id: Mapped[str | None] = mapped_column(Text, index=True)
    source_context_snapshot_json: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision: Mapped[str | None] = mapped_column(Text)
