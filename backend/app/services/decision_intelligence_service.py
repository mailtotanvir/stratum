from __future__ import annotations

from datetime import UTC, datetime
from collections import Counter

from app.models.decision_intelligence import (
    DecisionIntelligenceSummary,
    DecisionPatternEntry,
)
from app.services.decision_lineage_service import decision_lineage_service
from app.services.evaluation_reconstruction_service import (
    evaluation_reconstruction_service,
)
from app.services.proposal_service import proposal_service


class DecisionIntelligenceService:
    def build(self) -> DecisionIntelligenceSummary:
        records = decision_lineage_service.list_records()
        counter = Counter(record.decision_type for record in records)
        recurring = [
            DecisionPatternEntry(
                decision_key=decision_type,
                decision_type=decision_type,
                occurrences=count,
                failures=sum(1 for record in records if record.decision_type == decision_type and record.outcome != "accepted"),
                rationale=f"Decision type {decision_type} recurs across runtime sessions.",
            )
            for decision_type, count in counter.most_common()
        ]
        return DecisionIntelligenceSummary(
            generated_at=datetime.now(UTC),
            recurring_decisions=recurring,
            repeated_failures=recurring[:3],
            evaluation_history=[
                f"{item.projection_name}:{item.reconstruction_status}"
                for item in evaluation_reconstruction_service.inspect().projections
            ],
            proposal_outcomes=[
                f"{item.proposal_id}:{item.status}" for item in proposal_service.list_proposals()
            ],
            engineering_rationale=[
                record.metadata.get("rationale", record.decision_type)
                for record in records[:10]
            ],
        )


decision_intelligence_service = DecisionIntelligenceService()
