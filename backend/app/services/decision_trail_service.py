from app.models.decision_trail import DecisionTrail
from app.services.reconstruction_service import (
    ReconstructionService,
    reconstruction_service,
)


class DecisionTrailService:
    def __init__(
        self,
        reconstruction: ReconstructionService | None = None,
    ) -> None:
        self._reconstruction = reconstruction or reconstruction_service

    def reconstruct(self, proposal_id: str) -> DecisionTrail:
        return DecisionTrail.model_validate(
            self._reconstruction.reconstruct_decision_trail(proposal_id)
        )

    def reconstruct_all(self) -> list[DecisionTrail]:
        return [
            DecisionTrail.model_validate(trail)
            for trail in self._reconstruction.reconstruct_all_decision_trails()
        ]


decision_trail_service = DecisionTrailService()
