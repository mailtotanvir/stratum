from typing import Any

from app.models.runtime_event import Severity
from app.services.event_service import EventService, event_service


DEFAULT_ERROR_BUDGET_POLICY = {
    "warning_budget": 5,
    "error_budget": 2,
    "critical_budget": 0,
}


def classify_governance_status(severity_counts: dict[str, int]) -> str:
    if severity_counts[Severity.CRITICAL.value] > 0:
        return "critical"
    if (
        severity_counts[Severity.WARNING.value] > 0
        or severity_counts[Severity.ERROR.value] > 0
    ):
        return "degraded"
    return "ok"


class GovernanceService:
    def __init__(
        self,
        events: EventService | None = None,
        error_budget_policy: dict[str, int] | None = None,
    ) -> None:
        self._events = events or event_service
        self._error_budget_policy = (
            error_budget_policy or DEFAULT_ERROR_BUDGET_POLICY
        )

    def _severity_counts(self) -> dict[str, int]:
        severity_counts = {severity.value: 0 for severity in Severity}
        for event in self._events.list_persisted_events():
            severity_counts[event.severity.value] += 1
        return severity_counts

    def evaluate_error_budget(self) -> dict[str, Any]:
        severity_counts = self._severity_counts()
        usage = {
            "warnings": severity_counts[Severity.WARNING.value],
            "errors": severity_counts[Severity.ERROR.value],
            "criticals": severity_counts[Severity.CRITICAL.value],
        }

        policy = dict(self._error_budget_policy)
        remaining = {
            "warnings": policy["warning_budget"] - usage["warnings"],
            "errors": policy["error_budget"] - usage["errors"],
            "criticals": policy["critical_budget"] - usage["criticals"],
        }
        exhausted = {
            "warnings": usage["warnings"] > policy["warning_budget"],
            "errors": usage["errors"] > policy["error_budget"],
            "criticals": usage["criticals"] > policy["critical_budget"],
        }

        return {
            "policy": policy,
            "usage": usage,
            "remaining": remaining,
            "exhausted": exhausted,
            "status": (
                "budget_exhausted"
                if any(exhausted.values())
                else "within_budget"
            ),
        }

    def preview_decision(self) -> dict[str, Any]:
        severity_counts = self._severity_counts()
        governance_status = classify_governance_status(severity_counts)
        error_budget = self.evaluate_error_budget()
        has_critical = severity_counts[Severity.CRITICAL.value] > 0
        reasons: list[str] = []

        if has_critical:
            reasons.append("critical_event_present")
        if error_budget["status"] == "budget_exhausted":
            reasons.append("error_budget_exhausted")

        if reasons:
            decision = "block"
        elif governance_status == "degraded":
            decision = "warn"
            reasons.append("governance_degraded")
        else:
            decision = "allow"
            reasons.append("within_governance_policy")

        return {
            "decision": decision,
            "reasons": reasons,
            "governance_status": governance_status,
            "error_budget_status": error_budget["status"],
            "has_critical": has_critical,
        }

    def preview_reflection(self) -> dict[str, Any]:
        decision_preview = self.preview_decision()
        governance_status = decision_preview["governance_status"]
        error_budget_status = decision_preview["error_budget_status"]
        decision = decision_preview["decision"]
        reasons: list[str] = []

        if governance_status == "degraded":
            reasons.append("governance_degraded")
        if governance_status == "critical":
            reasons.append("governance_critical")
        if error_budget_status == "budget_exhausted":
            reasons.append("error_budget_exhausted")
        if decision in {"warn", "block"}:
            reasons.append("decision_preview_not_allow")

        recommended = bool(reasons)
        if not recommended:
            reasons.append("no_reflection_needed")

        return {
            "recommended": recommended,
            "reasons": reasons,
            "decision_preview": {
                "decision": decision,
                "reasons": decision_preview["reasons"],
            },
            "governance_status": governance_status,
            "error_budget_status": error_budget_status,
        }


governance_service = GovernanceService()
