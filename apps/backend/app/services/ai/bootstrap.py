"""Initialize AI providers from environment (OpenAI / Anthropic / custom)."""

from typing import Optional

from app.core.config import settings
from app.services.ai.providers import (
    configure_providers,
    get_provider_manager,
    AIRequest,
    OpenAIProvider,
    AnthropicProvider,
)

_configured = False


def _provider_from_doc(doc: dict):
    provider_type = (doc.get("provider_type") or "openai").lower()
    base_url = doc.get("base_url")
    api_key = doc.get("api_key") or ""
    if provider_type == "anthropic":
        return AnthropicProvider(api_key=api_key, base_url=base_url or "https://api.anthropic.com/v1")
    # OpenAI and OpenAI-compatible "custom" providers share the same protocol.
    return OpenAIProvider(api_key=api_key, base_url=base_url or "https://api.openai.com/v1")


def apply_org_provider(doc: dict) -> Optional[str]:
    """Register an org-level AI provider (Mongo ai_providers doc) into the runtime manager."""
    manager = get_provider_manager()
    key = str(doc.get("_id") or doc.get("name") or "org-ai-provider")
    manager.register(key, _provider_from_doc(doc))
    manager.set_active(key)

    models = doc.get("models") or []
    model_names = []
    for item in models:
        name = item.get("name") if isinstance(item, dict) else item
        if name:
            model_names.append(str(name))
    selected = doc.get("selected_model") or doc.get("model")
    if selected:
        model_names.insert(0, str(selected))
    if not model_names:
        model_names = [settings.ai_default_model]

    manager.configure_models({
        name: {
            "provider": key,
            "temperature": 0.7,
            "max_tokens": 500,
            "enabled": True,
            "cost_per_1k": 0.002,
        }
        for name in dict.fromkeys(model_names)
    })
    return key


async def get_active_org_provider(org_id: Optional[str]) -> Optional[dict]:
    """Return the active AI provider for an org, falling back to a platform-wide provider.

    Organization-specific providers always win over global (organization_id=None)
    providers. Within a scope the ``is_default`` provider wins, otherwise the most
    recently created active provider is used.
    """
    from app.db.mongodb import MongoDB

    coll = MongoDB.get_collection("ai_providers")

    async def _active_for(query: dict) -> Optional[dict]:
        cursor = coll.find({**query, "is_active": True}).sort("created_at", -1)
        docs = [d async for d in cursor]
        if not docs:
            return None
        return next((d for d in docs if d.get("is_default")), None) or docs[0]

    if org_id:
        org_provider = await _active_for({"organization_id": org_id})
        if org_provider:
            return org_provider
    return await _active_for({"organization_id": None})


def bootstrap_ai_providers() -> str:
    global _configured
    if _configured:
        return get_provider_manager()._active_provider or "none"

    provider = (settings.ai_provider or "openai").strip().lower()
    default_model = settings.ai_default_model
    config: dict = {}

    if settings.openai_api_key:
        config["openai"] = {
            "api_key": settings.openai_api_key,
            "base_url": settings.openai_base_url or "https://api.openai.com/v1",
            "default": provider == "openai",
            "models": {default_model: {"enabled": True}},
        }

    if settings.anthropic_api_key:
        config["anthropic"] = {
            "api_key": settings.anthropic_api_key,
            "base_url": settings.anthropic_base_url,
            "default": provider == "anthropic",
            "models": {default_model: {"enabled": True}},
        }

    configure_providers(config)
    _configured = True
    return get_provider_manager()._active_provider or "none"


async def bootstrap_ai_providers_for_org(org_id: Optional[str]) -> str:
    """Bootstrap env-based providers, then layer in the org's active AI provider if set."""
    active = bootstrap_ai_providers()
    if org_id:
        org_provider = await get_active_org_provider(org_id)
        if org_provider:
            apply_org_provider(org_provider)
            return str(org_provider.get("_id") or org_provider.get("name") or "org-ai-provider")
    return active or "none"


async def ai_runtime_status(organization_id: Optional[str] = None) -> dict:
    bootstrap_ai_providers()
    manager = get_provider_manager()
    provider = manager.get_active()
    provider_name = manager._active_provider or "none"
    model = settings.ai_default_model
    org_provider = None

    if organization_id:
        org_provider = await get_active_org_provider(organization_id)
        if org_provider:
            applied_key = apply_org_provider(org_provider)
            provider = manager.get_provider(applied_key) if applied_key else None
            provider_name = org_provider.get("name") or org_provider.get("provider_type") or applied_key or "none"
            model = org_provider.get("selected_model") or org_provider.get("model") or model

    healthy = False
    if provider:
        try:
            healthy = await provider.health_check()
        except Exception:
            healthy = False

    return {
        "provider": provider_name,
        "provider_type": (
            org_provider.get("provider_type") if organization_id and org_provider else provider_name
        ),
        "model": model,
        "status": "available" if healthy else "offline",
        "healthy": healthy,
        "providers": manager.list_providers(),
        "openai_configured": bool(settings.openai_api_key),
        "anthropic_configured": bool(settings.anthropic_api_key),
    }


async def generate_text(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 800,
    organization_id: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    bootstrap_ai_providers()
    manager = get_provider_manager()
    provider = manager.get_active()
    use_model = model or settings.ai_default_model

    if organization_id:
        org_provider = await get_active_org_provider(organization_id)
        if org_provider:
            applied_key = apply_org_provider(org_provider)
            provider = manager.get_provider(applied_key) if applied_key else None
            use_model = org_provider.get("selected_model") or org_provider.get("model") or use_model

    if not provider:
        return None, "No AI provider configured. Set OPENAI_API_KEY and AI_PROVIDER=openai on Render."

    try:
        response = await provider.generate(
            AIRequest(
                prompt=prompt,
                system=system,
                model=use_model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=settings.ai_timeout,
            )
        )
        return response.content, None
    except Exception as e:
        return None, str(e)
