from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from app.models.artifact_lineage import (
    ArtifactLineageRecord,
)
from app.models.decision_lineage import (
    DecisionLineageEvidenceSummary,
    DecisionLineageRecord,
)
from app.models.explainability import (
    ArtifactExplanation,
    DecisionExplanation,
    EvidenceExplanation,
    ExplanationView,
    GovernanceExplanation,
)
from app.models.governance_audit import GovernanceAuditRecord
from app.models.runtime_event import EventType, Severity
from app.models.runtime_reconstruction import RuntimeReconstructionView
from app.services.artifact_lineage_service import (
    ArtifactLineageNotFoundError,
    ArtifactLineageService,
    artifact_lineage_service,
)
from app.services.decision_lineage_service import (
    DecisionLineageNotFoundError,
    DecisionLineageService,
    decision_lineage_service,
)
from app.services.event_service import EventService, event_service
from app.services.governance_audit_service import (
    GovernanceAuditService,
    governance_audit_service,
)
from app.services.runtime_reconstruction_service import (
    RuntimeReconstructionService,
    runtime_reconstruction_service,
)
from app.services.runtime_session_service import RuntimeSessionNotFoundError


class ExplanationNotFoundError(LookupError):
    pass


class ExplanationGenerationError(RuntimeError):
    pass


class ExplainabilityService:
    def __init__(
        self,
        decisions: DecisionLineageService | None = None,
        governance: GovernanceAuditService | None = None,
        artifacts: ArtifactLineageService | None = None,
        reconstruction: RuntimeReconstructionService | None = None,
        events: EventService | None = None,
        clock: Callable[[], datetime] | None = None,
        timer: Callable[[], float] | None = None,
    ) -> None:
        self._decisions = decisions or decision_lineage_service
        self._governance = governance or governance_audit_service
        self._artifacts = artifacts or artifact_lineage_service
        self._reconstruction = reconstruction or runtime_reconstruction_service
        self._events = events or event_service
        self._clock = clock or (lambda: datetime.now(UTC))
        self._timer = timer or perf_counter
        self._generated_total = 0
        self._incomplete_total = 0
        self._failures_total = 0

    def explain_decision(self, decision_id: str) -> DecisionExplanation:
        started_at = self._timer()
        try:
            explanation = self._decision_explanation(decision_id)
        except DecisionLineageNotFoundError as exc:
            self._record_failure(started_at, "decision", decision_id, exc)
            raise ExplanationNotFoundError(str(exc)) from exc
        except Exception as exc:
            self._record_failure(started_at, "decision", decision_id, exc)
            raise ExplanationGenerationError(
                f"Decision explanation failed: {exc}"
            ) from exc

        self._record_success(started_at, "decision", decision_id, explanation)
        return explanation

    def explain_artifact(self, artifact_id: str) -> ArtifactExplanation:
        started_at = self._timer()
        try:
            explanation = self._artifact_explanation(artifact_id)
        except ArtifactLineageNotFoundError as exc:
            self._record_failure(started_at, "artifact", artifact_id, exc)
            raise ExplanationNotFoundError(str(exc)) from exc
        except Exception as exc:
            self._record_failure(started_at, "artifact", artifact_id, exc)
            raise ExplanationGenerationError(
                f"Artifact explanation failed: {exc}"
            ) from exc

        self._record_success(started_at, "artifact", artifact_id, explanation)
        return explanation

    def explain_session(self, session_id: str) -> ExplanationView:
        started_at = self._timer()
        try:
            view = self._session_explanation(session_id)
        except RuntimeSessionNotFoundError as exc:
            self._record_failure(started_at, "session", session_id, exc)
            raise ExplanationNotFoundError(str(exc)) from exc
        except Exception as exc:
            self._record_failure(started_at, "session", session_id, exc)
            raise ExplanationGenerationError(
                f"Session explanation failed: {exc}"
            ) from exc

        self._record_success(started_at, "session", session_id, view)
        return view

    def observability_metrics(self) -> dict[str, int]:
        return {
            "explanations_generated_total": self._generated_total,
            "incomplete_explanations_total": self._incomplete_total,
            "explanation_failures_total": self._failures_total,
        }

    def _decision_explanation(self, decision_id: str) -> DecisionExplanation:
        chain = self._decisions.get_chain(decision_id)
        if not chain.records:
            raise DecisionLineageNotFoundError(
                f"Decision lineage not found: {decision_id}"
            )
        record = chain.records[-1]
        if not isinstance(record, DecisionLineageRecord):
            raise TypeError("Malformed decision lineage record")
        incomplete_reasons: list[str] = []
        if not chain.complete:
            incomplete_reasons.append("decision_lineage_incomplete")
        incomplete_reasons.extend(
            str(reason)
            for reason in record.metadata.get("incomplete_reasons", [])
            if isinstance(reason, str)
        )
        evidence = self._safe_evidence(decision_id, incomplete_reasons)
        governance = self._governance_actions(decision_id)
        artifacts = [
            self._artifact_for_related_id(artifact_id, incomplete_reasons)
            for artifact_id in sorted(set(record.related_artifact_ids))
        ]
        reconstruction = self._safe_reconstruction(
            record.session_id,
            incomplete_reasons,
        )
        proposal_source = record.proposal_id
        if proposal_source is None and reconstruction is not None:
            proposal_source = self._proposal_from_reconstruction(
                reconstruction,
                record.decision_id,
            )
        complete = not incomplete_reasons and all(
            artifact.complete for artifact in artifacts
        )
        return DecisionExplanation(
            decision_id=record.decision_id,
            decision_type=record.decision_type,
            outcome=record.outcome,
            recommendation_source=record.recommendation_id,
            proposal_source=proposal_source,
            governance_actions=governance,
            evidence_summary=evidence,
            related_artifacts=artifacts,
            lineage_depth=record.lineage_depth,
            complete=complete,
            incomplete_reasons=sorted(set(incomplete_reasons)),
            metadata={
                "derived": True,
                "authoritative_source": "runtime_event_store",
                "projection_state_mutated": False,
                "chain_length": len(chain.records),
            },
        )

    def _artifact_explanation(self, artifact_id: str) -> ArtifactExplanation:
        chain = self._artifacts.get_chain(artifact_id)
        record = next(
            item for item in chain.records if item.artifact_id == artifact_id
        )
        if not isinstance(record, ArtifactLineageRecord):
            raise TypeError("Malformed artifact lineage record")
        incomplete_reasons: list[str] = []
        if not chain.complete:
            incomplete_reasons.append("artifact_lineage_incomplete")
        return self._artifact_from_record(
            record,
            complete=chain.complete,
            incomplete_reasons=incomplete_reasons,
        )

    def _session_explanation(self, session_id: str) -> ExplanationView:
        incomplete_reasons: list[str] = []
        reconstruction = self._reconstruction.reconstruct(session_id)
        decision_ids = [
            item.decision_id
            for item in reconstruction.decision_lineage_summaries
        ]
        decisions = [
            self._decision_for_session(decision_id, incomplete_reasons)
            for decision_id in sorted(set(decision_ids))
        ]
        artifact_ids = [
            item.artifact_id
            for item in reconstruction.artifact_lineage_summaries
        ]
        artifacts = [
            self._artifact_for_related_id(artifact_id, incomplete_reasons)
            for artifact_id in sorted(set(artifact_ids))
        ]
        governance = sorted(
            [
                self._governance_explanation(record)
                for record in self._governance.list_records()
                if getattr(record, "session_id", None) == session_id
            ],
            key=lambda item: (
                item.occurred_at,
                item.source_event_id,
                item.decision_id,
            ),
        )
        evidence = sorted(
            [
                item
                for decision in decisions
                for item in decision.evidence_summary
            ],
            key=lambda item: (item.source_event_id, item.evidence_id),
        )
        incomplete_reasons.extend(reconstruction.incomplete_reasons)
        complete = (
            not reconstruction.incomplete
            and not incomplete_reasons
            and all(decision.complete for decision in decisions)
            and all(artifact.complete for artifact in artifacts)
        )
        return ExplanationView(
            generated_at=self._clock(),
            subject_type="session",
            subject_id=session_id,
            decisions=decisions,
            artifacts=artifacts,
            governance_actions=governance,
            evidence=evidence,
            complete=complete,
            incomplete_reasons=sorted(set(incomplete_reasons)),
            metadata={
                "derived": True,
                "authoritative_source": "runtime_event_store",
                "projection_state_mutated": False,
                "reconstruction_incomplete": reconstruction.incomplete,
            },
        )

    def _safe_evidence(
        self,
        decision_id: str,
        incomplete_reasons: list[str],
    ) -> list[EvidenceExplanation]:
        try:
            summary = self._decisions.evidence_summary(decision_id)
        except Exception:
            incomplete_reasons.append("decision_evidence_unavailable")
            return []
        if not isinstance(summary, DecisionLineageEvidenceSummary):
            incomplete_reasons.append("malformed_decision_evidence")
            return []
        return [
            EvidenceExplanation(
                evidence_id=item.evidence_id,
                evidence_type=item.evidence_type,
                evidence_reference=item.evidence_reference,
                summary=item.summary,
                source_event_id=item.source_event_id,
            )
            for item in sorted(
                summary.evidence,
                key=lambda item: (item.source_event_id, item.evidence_id),
            )
        ]

    def _governance_actions(
        self,
        decision_id: str,
    ) -> list[GovernanceExplanation]:
        return sorted(
            [
                self._governance_explanation(record)
                for record in self._governance.list_records()
                if getattr(record, "decision_id", None) == decision_id
            ],
            key=lambda item: (
                item.occurred_at,
                item.source_event_id,
                item.decision_id,
            ),
        )

    @staticmethod
    def _governance_explanation(
        record: GovernanceAuditRecord,
    ) -> GovernanceExplanation:
        return GovernanceExplanation(
            decision_id=record.decision_id,
            decision_type=record.decision_type,
            outcome=record.outcome,
            actor=record.actor,
            occurred_at=record.occurred_at,
            evidence_count=record.evidence_count,
            policy_reference=record.policy_reference,
            budget_reference=record.budget_reference,
            reflection_reference=record.reflection_reference,
            source_event_id=record.source_event_id,
        )

    def _artifact_for_related_id(
        self,
        artifact_id: str,
        incomplete_reasons: list[str],
    ) -> ArtifactExplanation:
        try:
            return self._artifact_explanation(artifact_id)
        except ArtifactLineageNotFoundError:
            incomplete_reasons.append(f"missing_artifact_lineage:{artifact_id}")
            return ArtifactExplanation(
                artifact_id=artifact_id,
                lineage_status="missing",
                complete=False,
                incomplete_reasons=["missing_artifact_lineage"],
            )

    @staticmethod
    def _artifact_from_record(
        record: ArtifactLineageRecord,
        *,
        complete: bool,
        incomplete_reasons: list[str],
    ) -> ArtifactExplanation:
        reasons = list(incomplete_reasons)
        if record.lineage_status != "linked":
            reasons.append(f"artifact_lineage_{record.lineage_status}")
        return ArtifactExplanation(
            artifact_id=record.artifact_id,
            artifact_path=record.artifact_path,
            artifact_type=record.artifact_type,
            lineage_status=record.lineage_status,
            decision_id=record.decision_id,
            proposal_id=record.proposal_id,
            producing_tool_invocation_id=record.producing_tool_invocation_id,
            parent_artifact_ids=sorted(set(record.parent_artifact_ids)),
            related_event_ids=sorted(set(record.related_event_ids)),
            complete=complete and not reasons,
            incomplete_reasons=sorted(set(reasons)),
        )

    def _decision_for_session(
        self,
        decision_id: str,
        incomplete_reasons: list[str],
    ) -> DecisionExplanation:
        try:
            return self._decision_explanation(decision_id)
        except Exception:
            incomplete_reasons.append(f"decision_explanation_unavailable:{decision_id}")
            return DecisionExplanation(
                decision_id=decision_id,
                decision_type="unknown",
                outcome="unknown",
                lineage_depth=0,
                complete=False,
                incomplete_reasons=["decision_explanation_unavailable"],
            )

    def _safe_reconstruction(
        self,
        session_id: str | None,
        incomplete_reasons: list[str],
    ) -> RuntimeReconstructionView | None:
        if session_id is None:
            incomplete_reasons.append("missing_session_reference")
            return None
        try:
            reconstruction = self._reconstruction.reconstruct(session_id)
        except Exception:
            incomplete_reasons.append("runtime_reconstruction_unavailable")
            return None
        if reconstruction.incomplete:
            incomplete_reasons.extend(reconstruction.incomplete_reasons)
        return reconstruction

    @staticmethod
    def _proposal_from_reconstruction(
        reconstruction: RuntimeReconstructionView,
        decision_id: str,
    ) -> str | None:
        decision = next(
            (
                item
                for item in reconstruction.decision_lineage_summaries
                if item.decision_id == decision_id
            ),
            None,
        )
        return decision.proposal_id if decision is not None else None

    def _record_success(
        self,
        started_at: float,
        subject_type: str,
        subject_id: str,
        explanation: DecisionExplanation | ArtifactExplanation | ExplanationView,
    ) -> None:
        self._generated_total += 1
        incomplete = not explanation.complete
        if incomplete:
            self._incomplete_total += 1
        self._events.emit_event_sync(
            event_type=(
                EventType.EXPLANATION_INCOMPLETE
                if incomplete
                else EventType.EXPLANATION_GENERATED
            ),
            severity=Severity.WARNING if incomplete else Severity.INFO,
            message=(
                f"Explanation incomplete: {subject_type}:{subject_id}"
                if incomplete
                else f"Explanation generated: {subject_type}:{subject_id}"
            ),
            metadata={
                "subject_type": subject_type,
                "subject_id": subject_id,
                "duration_ms": self._duration_ms(started_at),
                "incomplete": incomplete,
                "incomplete_reasons": explanation.incomplete_reasons,
                **self.observability_metrics(),
            },
        )

    def _record_failure(
        self,
        started_at: float,
        subject_type: str,
        subject_id: str,
        exc: Exception,
    ) -> None:
        self._failures_total += 1
        self._events.emit_event_sync(
            event_type=EventType.EXPLANATION_FAILED,
            severity=Severity.ERROR,
            message=f"Explanation failed: {subject_type}:{subject_id}",
            metadata={
                "subject_type": subject_type,
                "subject_id": subject_id,
                "error_type": type(exc).__name__,
                "duration_ms": self._duration_ms(started_at),
                **self.observability_metrics(),
            },
        )

    def _duration_ms(self, started_at: float) -> float:
        return round(max(0.0, (self._timer() - started_at) * 1000), 3)


explainability_service = ExplainabilityService()
