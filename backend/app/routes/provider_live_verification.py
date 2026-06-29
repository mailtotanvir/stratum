from fastapi import APIRouter

from app.models.provider_live_verification import ProviderLiveVerification
from app.services.provider_live_verification_service import (
    provider_live_verification_service,
)


router = APIRouter()


@router.get("/providers/live/verify")
def verify_live_provider() -> ProviderLiveVerification:
    return provider_live_verification_service.verify()
