from app.models.provider_configuration import ProviderConfiguration


class ProviderAuthenticationService:
    """Build provider authentication metadata from configuration.

    Secrets stay out of top-level ProviderConfiguration fields.
    """

    def headers_for(
        self,
        configuration: ProviderConfiguration,
    ) -> dict[str, str]:
        api_key = self.api_key(configuration)
        if api_key is None:
            return {}
        return {"Authorization": f"Bearer {api_key}"}

    def api_key(
        self,
        configuration: ProviderConfiguration,
    ) -> str | None:
        value = configuration.metadata.get("api_key")
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None


provider_authentication_service = ProviderAuthenticationService()
