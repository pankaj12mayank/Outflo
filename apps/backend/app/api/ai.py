"""
AI API Endpoints — OpenAI / Anthropic / custom OpenAI-compatible providers.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from datetime import datetime

from app.middleware import get_current_user_or_system_owner
from app.services.ai.bootstrap import ai_runtime_status, generate_text, get_active_org_provider
from app.core.config import settings
from app.db.mongodb import MongoDB
from app.services.auth_service import PermissionChecker

router = APIRouter(prefix="/ai", tags=["AI"])


def _ensure_ai_permission(current_user: dict, action: str) -> None:
    if not PermissionChecker.has_permission(current_user.get("role"), "ai", action):
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied. Required: ai:{action}",
        )


async def ai_read_user(current_user: dict = Depends(get_current_user_or_system_owner)) -> dict:
    _ensure_ai_permission(current_user, "read")
    return current_user


async def ai_write_user(current_user: dict = Depends(get_current_user_or_system_owner)) -> dict:
    _ensure_ai_permission(current_user, "write")
    return current_user


async def ai_manage_user(current_user: dict = Depends(get_current_user_or_system_owner)) -> dict:
    _ensure_ai_permission(current_user, "manage")
    return current_user


class AIRequest(BaseModel):
    content: Optional[str] = None
    prompt: Optional[str] = None
    lead_data: Optional[dict] = None
    template: Optional[str] = None


class PersonalizeRequest(BaseModel):
    lead_name: str
    company_name: str
    template: str
    custom_fields: Optional[dict] = None


class ClassifyRequest(BaseModel):
    email_text: str
    subject: Optional[str] = None


class EnrichRequest(BaseModel):
    website_url: str
    lead_email: str


@router.get("/status")
async def get_ai_status(current_user: dict = Depends(ai_read_user)):
    """AI provider status (OpenAI, Anthropic, or custom OpenAI-compatible)."""
    status = await ai_runtime_status(current_user.get("organization_id"))
    return {
        "status": "available" if status["healthy"] else "offline",
        "provider": status["provider"],
        "model": status["model"],
        "healthy": status["healthy"],
        "providers": status["providers"],
        "message": (
            f"Connected via {status['provider']}"
            if status["healthy"]
            else "AI provider is offline. Add an active provider in AI Providers or check its base URL / API key."
        ),
    }


@router.get("/models")
async def list_models(current_user: dict = Depends(ai_read_user)):
    """List models from the organization's active AI provider."""
    org_id = current_user.get("organization_id")
    status = await ai_runtime_status(org_id)
    provider_doc = await get_active_org_provider(org_id)
    models: list[dict] = []
    if provider_doc:
        for item in provider_doc.get("models") or []:
            name = item.get("name") if isinstance(item, dict) else item
            if name:
                models.append({"name": str(name), "provider": provider_doc.get("provider_type")})
    if (
        status["provider"] != "none"
        and status["model"]
        and status["model"] not in [m["name"] for m in models]
    ):
        models.insert(0, {"name": status["model"], "provider": status.get("provider_type") or status["provider"]})
    return {
        "models": models,
        "provider": status["provider"],
        "selected_model": status["model"],
    }


@router.post("/personalize")
async def personalize_content(
    request: PersonalizeRequest,
    current_user: dict = Depends(ai_write_user),
):
    prompt = f"""Generate a personalized email opening line for:
- Recipient: {request.lead_name}
- Company: {request.company_name}
- Template context: {request.template}

Generate 1-2 natural sentences only."""

    content, err = await generate_text(prompt, max_tokens=200, organization_id=current_user.get("organization_id"))
    if content:
        return {"personalized": True, "content": content, "method": "ai"}

    personalized = request.template.replace("{{name}}", request.lead_name)
    personalized = personalized.replace("{{company}}", request.company_name)
    return {
        "personalized": True,
        "content": personalized,
        "method": "template_fallback",
        "error": err,
    }


@router.post("/classify-reply")
async def classify_reply(
    request: ClassifyRequest,
    current_user: dict = Depends(ai_write_user),
):
    prompt = f"""Classify this email reply into ONE category only:
interested, not_interested, maybe, pricing_inquiry, meeting_request, out_of_office

Subject: {request.subject or 'N/A'}
Body: {request.email_text[:500]}

Reply with the category name only."""

    content, err = await generate_text(
        prompt,
        max_tokens=50,
        temperature=0.2,
        organization_id=current_user.get("organization_id"),
    )
    if not content:
        return {
            "classification": "unknown",
            "confidence": 0,
            "suggested_action": "manual_review",
            "error": err,
        }

    classification = content.strip().lower()
    category_map = {
        "interested": {"category": "interested", "action": "notify_sales"},
        "not_interested": {"category": "not_interested", "action": "archive"},
        "maybe": {"category": "maybe", "action": "follow_up"},
        "pricing_inquiry": {"category": "pricing", "action": "send_pricing"},
        "meeting_request": {"category": "meeting", "action": "schedule_call"},
        "out_of_office": {"category": "out_of_office", "action": "wait_and_follow"},
    }
    result = category_map.get(classification.replace(" ", "_"), {
        "category": classification,
        "action": "manual_review",
    })
    return {
        "classification": result["category"],
        "confidence": 0.85,
        "suggested_action": result["action"],
        "raw_response": classification,
    }


@router.post("/enrich-lead")
async def enrich_lead(
    request: EnrichRequest,
    current_user: dict = Depends(ai_write_user),
):
    return {
        "enriched": True,
        "data": {
            "website": request.website_url,
            "email": request.lead_email,
            "niche": "B2B",
            "note": "Full scrape enrichment runs via /api/v1/scraping endpoints",
        },
    }


@router.post("/generate-email")
async def generate_email(
    request: AIRequest,
    current_user: dict = Depends(ai_write_user),
):
    prompt = f"""Write a professional cold outreach email with subject line, body, and CTA.
Context: {request.prompt or request.content or 'General B2B outreach'}"""

    content, err = await generate_text(prompt, max_tokens=600, organization_id=current_user.get("organization_id"))
    if content:
        return {"generated": True, "content": content}
    raise HTTPException(status_code=503, detail=err or "AI unavailable")


@router.get("/config")
async def get_ai_config(current_user: dict = Depends(ai_read_user)):
    """Non-secret AI config for admin UI."""
    return {
        "ai_provider": settings.ai_provider,
        "ai_default_model": settings.ai_default_model,
        "openai_configured": bool(settings.openai_api_key),
        "anthropic_configured": bool(settings.anthropic_api_key),
        "openai_base_url": settings.openai_base_url if settings.openai_api_key else None,
    }


# ── Frontend-facing aliases ──────────────────────────────────────────

@router.post("/generate")
async def generate(
    request: AIRequest,
    current_user: dict = Depends(ai_write_user),
):
    return await generate_email(request, current_user)


@router.post("/enrich")
async def enrich(
    request: EnrichRequest,
    current_user: dict = Depends(ai_write_user),
):
    return await enrich_lead(request, current_user)


@router.post("/analyze-reply")
async def analyze_reply(
    request: ClassifyRequest,
    current_user: dict = Depends(ai_write_user),
):
    return await classify_reply(request, current_user)


# ── AI Prompts CRUD ──────────────────────────────────────────────────

@router.get("/prompts")
async def list_prompts(
    category: Optional[str] = None,
    current_user: dict = Depends(ai_read_user),
):
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("ai_prompts")
    query = {"organization_id": org_id}
    if category:
        query["category"] = category
    cursor = coll.find(query).sort("created_at", -1)
    prompts = []
    async for doc in cursor:
        prompts.append({
            "id": str(doc["_id"]),
            "name": doc.get("name"),
            "content": doc.get("content"),
            "category": doc.get("category"),
            "created_at": doc.get("created_at"),
        })
    return prompts


@router.post("/prompts")
async def create_prompt(
    data: dict,
    current_user: dict = Depends(ai_write_user),
):
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("ai_prompts")
    doc = {
        "organization_id": org_id,
        "name": data.get("name"),
        "content": data.get("content"),
        "category": data.get("category", "general"),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    result = await coll.insert_one(doc)
    return {"id": str(result.inserted_id), **doc}


@router.patch("/prompts/{prompt_id}")
async def update_prompt(
    prompt_id: str,
    data: dict,
    current_user: dict = Depends(ai_write_user),
):
    from bson import ObjectId
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("ai_prompts")
    update = {k: v for k, v in data.items() if k in ("name", "content", "category")}
    update["updated_at"] = datetime.utcnow().isoformat()
    result = await coll.update_one(
        {"_id": ObjectId(prompt_id), "organization_id": org_id},
        {"$set": update},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Prompt not found")
    return {"success": True}


@router.delete("/prompts/{prompt_id}")
async def delete_prompt(
    prompt_id: str,
    current_user: dict = Depends(ai_write_user),
):
    from bson import ObjectId
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("ai_prompts")
    result = await coll.delete_one({"_id": ObjectId(prompt_id), "organization_id": org_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Prompt not found")
    return {"success": True}


# ── AI Settings ──────────────────────────────────────────────────────

@router.get("/settings")
async def get_ai_settings(current_user: dict = Depends(ai_read_user)):
    await MongoDB.connect()
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("ai_settings")
    doc = await coll.find_one({"organization_id": org_id})
    if not doc:
        return {
            "provider": settings.ai_provider or "openai",
            "model": settings.ai_default_model or "gpt-4o-mini",
            "temperature": 0.7,
            "max_tokens": 1024,
        }
    return {
        "provider": doc.get("provider", settings.ai_provider),
        "model": doc.get("model", settings.ai_default_model),
        "temperature": doc.get("temperature", 0.7),
        "max_tokens": doc.get("max_tokens", 1024),
    }


@router.patch("/settings")
async def update_ai_settings(
    data: dict,
    current_user: dict = Depends(ai_write_user),
):
    await MongoDB.connect()
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("ai_settings")
    allowed = {"provider", "model", "temperature", "max_tokens"}
    update = {k: v for k, v in data.items() if k in allowed}
    await coll.update_one(
        {"organization_id": org_id},
        {"$set": {**update, "updated_at": datetime.utcnow().isoformat()}},
        upsert=True,
    )
    return {"success": True}


# ── Usage ────────────────────────────────────────────────────────────

@router.get("/usage")
async def get_ai_usage(
    period: str = "month",
    current_user: dict = Depends(ai_read_user),
):
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("ai_usage")
    pipeline = [
        {"$match": {"organization_id": org_id}},
        {"$group": {
            "_id": None,
            "total_requests": {"$sum": 1},
            "total_tokens": {"$sum": "$tokens"},
        }},
    ]
    result = []
    async for doc in coll.aggregate(pipeline):
        result.append(doc)
    if result:
        return {"total_requests": result[0]["total_requests"], "total_tokens": result[0]["total_tokens"]}
    return {"total_requests": 0, "total_tokens": 0}


# ── Website Analyzer ─────────────────────────────────────────────────

@router.post("/website/analyze")
async def analyze_website(
    data: dict,
    current_user: dict = Depends(ai_write_user),
):
    url = data.get("url", "")
    prompt = f"Analyze this website URL and describe its business: {url}"
    content, err = await generate_text(prompt, max_tokens=300, organization_id=current_user.get("organization_id"))
    if content:
        return {"analyzed": True, "summary": content, "url": url}
    return {"analyzed": True, "summary": f"Website at {url}", "url": url, "error": err}


# =============================================================================
# AI Provider Configuration CRUD
# =============================================================================

ALLOWED_PROVIDER_TYPES = {"openai", "anthropic", "custom"}

DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "custom": "",
}


class AIProviderBase(BaseModel):
    name: str
    provider_type: str  # openai, anthropic, custom
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    is_active: bool = True
    is_default: bool = False


class AIProviderCreate(AIProviderBase):
    models: list = []
    selected_model: Optional[str] = None
    organization_id: Optional[str] = None  # system owner only


class AIProviderUpdate(BaseModel):
    name: Optional[str] = None
    provider_type: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    models: Optional[list] = None
    selected_model: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


class AIProviderResponse(BaseModel):
    id: str
    name: str
    provider_type: str
    base_url: Optional[str] = None
    api_key_configured: bool = False
    api_key_hint: Optional[str] = None
    is_active: bool
    is_default: bool
    models: list = []
    selected_model: Optional[str] = None
    organization_id: Optional[str] = None
    created_at: str
    updated_at: str


class TestProviderRequest(BaseModel):
    provider_id: Optional[str] = None
    provider_type: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None


class FetchModelsRequest(BaseModel):
    provider_id: Optional[str] = None
    provider_type: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None


def _normalize_role(role: Optional[str]) -> str:
    return (role or "").strip().lower()


def _is_system_owner(user: dict) -> bool:
    return _normalize_role(user.get("role")) == "system_owner"


def _org_id(user: dict) -> Optional[str]:
    value = user.get("organization_id")
    return str(value) if value else None


def _parse_object_id(value: str):
    from bson import ObjectId

    try:
        return ObjectId(value)
    except Exception:
        raise HTTPException(status_code=404, detail="Provider not found")


def _scope_query(user: dict) -> dict:
    """System owners can manage every provider; org users only their own."""
    if _is_system_owner(user):
        return {}
    org_id = _org_id(user)
    return {"organization_id": org_id} if org_id else {"organization_id": None}


def _can_manage_doc(user: dict, doc: dict) -> bool:
    if _is_system_owner(user):
        return True
    org_id = _org_id(user)
    return bool(org_id) and doc.get("organization_id") == org_id


def _normalize_base_url(provider_type: str, base_url: Optional[str]) -> Optional[str]:
    if base_url is not None:
        base_url = base_url.strip().rstrip("/")
    if not base_url:
        return DEFAULT_BASE_URLS.get(provider_type) or None
    return base_url


def _normalize_models(models) -> list[dict]:
    normalized: list[dict] = []
    seen: set[str] = set()
    for item in models or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            provider = item.get("provider")
        else:
            name = str(item or "").strip()
            provider = None
        if not name or name in seen:
            continue
        seen.add(name)
        entry = {"name": name}
        if provider:
            entry["provider"] = str(provider)
        normalized.append(entry)
    return normalized


def _model_names(models) -> list[str]:
    names = []
    for item in models or []:
        name = item.get("name") if isinstance(item, dict) else item
        if name:
            names.append(str(name))
    return list(dict.fromkeys(names))


def _with_selected_model(models: list[dict], selected_model: Optional[str]) -> list[dict]:
    if selected_model and selected_model not in _model_names(models):
        models = [*models, {"name": selected_model}]
    return models


def _mask_key(key: Optional[str]) -> str:
    if not key:
        return ""
    return "*" * 8 + key[-4:] if len(key) > 4 else "*" * 8


def _provider_response(doc: dict) -> AIProviderResponse:
    api_key = doc.get("api_key")
    return AIProviderResponse(
        id=str(doc["_id"]),
        name=doc.get("name") or "",
        provider_type=doc.get("provider_type") or "",
        base_url=doc.get("base_url"),
        api_key_configured=bool(api_key),
        api_key_hint=_mask_key(api_key) if api_key else None,
        is_active=doc.get("is_active", True),
        is_default=bool(doc.get("is_default", False)),
        models=doc.get("models") or [],
        selected_model=doc.get("selected_model"),
        organization_id=str(doc["organization_id"]) if doc.get("organization_id") else None,
        created_at=doc.get("created_at") or "",
        updated_at=doc.get("updated_at") or "",
    )


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _upstream_error(response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error)
            if error:
                return str(error)
            return str(body.get("message") or body.get("detail") or body)
    except Exception:
        pass
    text = (response.text or "").strip()
    return text[:300] if text else f"HTTP {response.status_code}"


async def _fetch_models_for_provider(
    provider_type: Optional[str],
    base_url: Optional[str],
    api_key: Optional[str],
) -> tuple[bool, str, list[dict]]:
    """Probe an AI provider and return its available models."""
    import httpx

    provider_type = (provider_type or "").strip().lower()
    if provider_type not in ALLOWED_PROVIDER_TYPES:
        return False, f"Unsupported provider type: {provider_type or 'missing'}", []

    base = _normalize_base_url(provider_type, base_url)
    headers: dict[str, str] = {}
    if provider_type == "anthropic":
        headers = {"x-api-key": api_key or "", "anthropic-version": "2023-06-01"}
    elif api_key:
        headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=8.0),
            follow_redirects=True,
            headers=headers,
        ) as client:
            if provider_type == "anthropic":
                response = await client.get(_join_url(base or DEFAULT_BASE_URLS["anthropic"], "models"))
                if response.status_code == 200:
                    models = [
                        {"name": m.get("id") or "", "provider": "anthropic"}
                        for m in response.json().get("data", [])
                    ]
                    if models:
                        models = [m for m in models if m["name"]]
                        return True, f"Connected. {len(models)} model(s) available.", models
                if response.status_code in (401, 403):
                    return False, f"Invalid API key ({response.status_code}): {_upstream_error(response)}", []
                # Some Anthropic-compatible proxies do not expose /models.
                return True, "Connected (using built-in Anthropic model list).", [
                    {"name": "claude-3-5-sonnet-20241022", "provider": "anthropic"},
                    {"name": "claude-3-5-haiku-20241022", "provider": "anthropic"},
                    {"name": "claude-3-opus-20240229", "provider": "anthropic"},
                ]
            else:
                response = await client.get(_join_url(base or DEFAULT_BASE_URLS["openai"], "models"))
                if response.status_code != 200:
                    return False, f"Invalid API key or endpoint ({response.status_code}): {_upstream_error(response)}", []
                payload = response.json()
                models = [
                    {"name": m.get("id") or "", "provider": provider_type}
                    for m in payload.get("data", [])
                ]

        models = [m for m in models if m["name"]]
        return True, f"Connected. {len(models)} model(s) available.", models
    except httpx.TimeoutException:
        return False, "Connection timed out. Check the base URL and network.", []
    except httpx.ConnectError as exc:
        return False, f"Cannot connect to provider: {exc}", []
    except Exception as exc:
        return False, str(exc), []


@router.get("/providers", response_model=list[AIProviderResponse])
async def list_providers(current_user: dict = Depends(ai_read_user)):
    """List AI providers visible to the current user (sorted A to Z by name)."""
    await MongoDB.connect()
    coll = MongoDB.get_collection("ai_providers")
    cursor = coll.find(_scope_query(current_user)).sort([("name", 1), ("created_at", -1)])
    providers = []
    async for doc in cursor:
        providers.append(_provider_response(doc))
    return providers


@router.post("/providers", response_model=AIProviderResponse)
async def create_provider(
    data: AIProviderCreate,
    current_user: dict = Depends(ai_manage_user),
):
    """Create a new AI provider."""
    await MongoDB.connect()

    provider_type = (data.provider_type or "").strip().lower()
    if provider_type not in ALLOWED_PROVIDER_TYPES:
        raise HTTPException(400, f"Unsupported provider type: {data.provider_type}")

    name = (data.name or "").strip()
    if not name:
        raise HTTPException(400, "Provider name is required")

    base_url = _normalize_base_url(provider_type, data.base_url)
    if provider_type == "custom" and not base_url:
        raise HTTPException(400, "Base URL is required for a custom provider")

    if _is_system_owner(current_user):
        org_id = str(data.organization_id) if data.organization_id else None
    else:
        org_id = _org_id(current_user)
        if not org_id:
            raise HTTPException(400, "User must belong to an organization")

    coll = MongoDB.get_collection("ai_providers")
    if data.is_default:
        await coll.update_many(
            {"organization_id": org_id, "is_default": True},
            {"$set": {"is_default": False}},
        )

    existing_count = await coll.count_documents({"organization_id": org_id})
    is_default = bool(data.is_default or (existing_count == 0 and data.is_active))
    models = _normalize_models(data.models)
    models = _with_selected_model(models, data.selected_model)

    now = datetime.utcnow().isoformat()
    doc = {
        "organization_id": org_id,
        "name": name,
        "provider_type": provider_type,
        "base_url": base_url,
        "api_key": (data.api_key or "").strip() or None,
        "is_active": bool(data.is_active),
        "is_default": is_default,
        "models": models,
        "selected_model": data.selected_model,
        "created_at": now,
        "updated_at": now,
    }
    result = await coll.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _provider_response(doc)


@router.patch("/providers/{provider_id}", response_model=AIProviderResponse)
async def update_provider(
    provider_id: str,
    data: AIProviderUpdate,
    current_user: dict = Depends(ai_manage_user),
):
    """Update an AI provider (edit, toggle active/inactive, set default)."""
    await MongoDB.connect()
    oid = _parse_object_id(provider_id)
    coll = MongoDB.get_collection("ai_providers")

    doc = await coll.find_one({"_id": oid})
    if not doc:
        raise HTTPException(404, "Provider not found")
    if not _can_manage_doc(current_user, doc):
        raise HTTPException(403, "You cannot manage this provider")

    raw = data.model_dump(exclude_unset=True)
    update: dict = {}
    for field in ("name", "provider_type", "base_url", "api_key", "models", "selected_model", "is_active", "is_default"):
        if field in raw:
            update[field] = raw[field]

    if "name" in update:
        update["name"] = (update["name"] or "").strip()
        if not update["name"]:
            raise HTTPException(400, "Provider name is required")

    if "provider_type" in update:
        update["provider_type"] = (update["provider_type"] or "").strip().lower()
        if update["provider_type"] not in ALLOWED_PROVIDER_TYPES:
            raise HTTPException(400, f"Unsupported provider type: {update['provider_type']}")

    effective_type = update.get("provider_type", doc.get("provider_type") or "openai")
    if "base_url" in update:
        update["base_url"] = _normalize_base_url(effective_type, update["base_url"])
    if update.get("provider_type") == "custom" and not update.get("base_url", doc.get("base_url")):
        raise HTTPException(400, "Base URL is required for a custom provider")

    if "api_key" in update:
        update["api_key"] = (update["api_key"] or "").strip() or None

    if "models" in update:
        update["models"] = _normalize_models(update["models"])
    if "models" in update or "selected_model" in update:
        selected = update.get("selected_model", doc.get("selected_model"))
        update["models"] = _with_selected_model(update.get("models", doc.get("models") or []), selected)

    if update.get("is_default") is True:
        await coll.update_many(
            {"organization_id": doc.get("organization_id"), "is_default": True, "_id": {"$ne": oid}},
            {"$set": {"is_default": False}},
        )
    if update.get("is_active") is False:
        update["is_default"] = False

    update["updated_at"] = datetime.utcnow().isoformat()
    await coll.update_one({"_id": oid}, {"$set": update})

    updated = await coll.find_one({"_id": oid})
    return _provider_response(updated)


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: str,
    current_user: dict = Depends(ai_manage_user),
):
    """Delete an AI provider."""
    await MongoDB.connect()
    oid = _parse_object_id(provider_id)
    coll = MongoDB.get_collection("ai_providers")

    doc = await coll.find_one({"_id": oid})
    if not doc:
        raise HTTPException(404, "Provider not found")
    if not _can_manage_doc(current_user, doc):
        raise HTTPException(403, "You cannot manage this provider")

    await coll.delete_one({"_id": oid})

    if doc.get("is_default"):
        replacement = await coll.find_one(
            {"organization_id": doc.get("organization_id"), "is_active": True},
            sort=[("created_at", 1)],
        )
        if replacement:
            await coll.update_one({"_id": replacement["_id"]}, {"$set": {"is_default": True}})

    return {"success": True}


@router.post("/providers/fetch-models")
async def fetch_draft_models(
    data: FetchModelsRequest,
    current_user: dict = Depends(ai_manage_user),
):
    """Fetch models for an unsaved provider form (uses the saved key when editing)."""
    await MongoDB.connect()

    provider_type = data.provider_type
    base_url = data.base_url
    api_key = data.api_key

    if data.provider_id:
        oid = _parse_object_id(data.provider_id)
        coll = MongoDB.get_collection("ai_providers")
        doc = await coll.find_one({"_id": oid})
        if not doc:
            raise HTTPException(404, "Provider not found")
        if not _can_manage_doc(current_user, doc):
            raise HTTPException(403, "You cannot manage this provider")
        provider_type = provider_type or doc.get("provider_type")
        base_url = base_url or doc.get("base_url")
        api_key = api_key or doc.get("api_key")

    if not provider_type:
        raise HTTPException(400, "Provider type is required")

    success, message, models = await _fetch_models_for_provider(provider_type, base_url, api_key)
    return {"success": success, "message": message, "models": models, "count": len(models)}


@router.post("/providers/test")
async def test_provider(
    data: TestProviderRequest,
    current_user: dict = Depends(ai_manage_user),
):
    """Test AI provider connection."""
    await MongoDB.connect()

    provider_type = data.provider_type
    base_url = data.base_url
    api_key = data.api_key

    if data.provider_id:
        oid = _parse_object_id(data.provider_id)
        coll = MongoDB.get_collection("ai_providers")
        doc = await coll.find_one({"_id": oid})
        if not doc:
            raise HTTPException(404, "Provider not found")
        if not _can_manage_doc(current_user, doc):
            raise HTTPException(403, "You cannot manage this provider")
        provider_type = provider_type or doc.get("provider_type")
        base_url = base_url or doc.get("base_url")
        api_key = api_key or doc.get("api_key")

    if not provider_type:
        raise HTTPException(400, "Provider type is required")

    success, message, models = await _fetch_models_for_provider(provider_type, base_url, api_key)
    return {"success": success, "message": message, "models": models}


@router.post("/providers/{provider_id}/models")
async def fetch_provider_models(
    provider_id: str,
    current_user: dict = Depends(ai_manage_user),
):
    """Fetch available models for a saved provider and store them."""
    await MongoDB.connect()
    oid = _parse_object_id(provider_id)
    coll = MongoDB.get_collection("ai_providers")
    doc = await coll.find_one({"_id": oid})
    if not doc:
        raise HTTPException(404, "Provider not found")
    if not _can_manage_doc(current_user, doc):
        raise HTTPException(403, "You cannot manage this provider")

    success, message, models = await _fetch_models_for_provider(
        doc.get("provider_type"),
        doc.get("base_url"),
        doc.get("api_key"),
    )
    if not success:
        return {
            "success": False,
            "message": message,
            "models": doc.get("models") or [],
            "count": len(doc.get("models") or []),
        }

    update: dict = {
        "models": models,
        "updated_at": datetime.utcnow().isoformat(),
    }
    selected_model = doc.get("selected_model")
    if not selected_model and models:
        selected_model = models[0]["name"]
        update["selected_model"] = selected_model
    await coll.update_one({"_id": oid}, {"$set": update})

    return {
        "success": True,
        "message": message,
        "models": models,
        "count": len(models),
        "selected_model": selected_model,
    }
