"""
AI API Endpoints — OpenAI / Anthropic / Ollama via provider manager.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from datetime import datetime

from app.middleware import get_current_user
from app.services.ai.bootstrap import ai_runtime_status, generate_text
from app.core.config import settings
from app.db.mongodb import MongoDB

router = APIRouter(prefix="/ai", tags=["AI"])


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
async def get_ai_status(current_user: dict = Depends(get_current_user)):
    """AI provider status (OpenAI, Anthropic, or Ollama)."""
    status = await ai_runtime_status()
    return {
        "status": "available" if status["healthy"] else "offline",
        "provider": status["provider"],
        "model": status["model"],
        "healthy": status["healthy"],
        "providers": status["providers"],
        "message": (
            f"Connected via {status['provider']}"
            if status["healthy"]
            else "Configure OPENAI_API_KEY + AI_PROVIDER=openai for cloud deploy"
        ),
    }


@router.get("/models")
async def list_models(current_user: dict = Depends(get_current_user)):
    """List configured default model."""
    status = await ai_runtime_status()
    return {
        "models": [{"name": status["model"], "provider": status["provider"]}],
        "provider": status["provider"],
    }


@router.post("/personalize")
async def personalize_content(
    request: PersonalizeRequest,
    current_user: dict = Depends(get_current_user),
):
    prompt = f"""Generate a personalized email opening line for:
- Recipient: {request.lead_name}
- Company: {request.company_name}
- Template context: {request.template}

Generate 1-2 natural sentences only."""

    content, err = await generate_text(prompt, max_tokens=200)
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
    current_user: dict = Depends(get_current_user),
):
    prompt = f"""Classify this email reply into ONE category only:
interested, not_interested, maybe, pricing_inquiry, meeting_request, out_of_office

Subject: {request.subject or 'N/A'}
Body: {request.email_text[:500]}

Reply with the category name only."""

    content, err = await generate_text(prompt, max_tokens=50, temperature=0.2)
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
    current_user: dict = Depends(get_current_user),
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
    current_user: dict = Depends(get_current_user),
):
    prompt = f"""Write a professional cold outreach email with subject line, body, and CTA.
Context: {request.prompt or request.content or 'General B2B outreach'}"""

    content, err = await generate_text(prompt, max_tokens=600)
    if content:
        return {"generated": True, "content": content}
    raise HTTPException(status_code=503, detail=err or "AI unavailable")


@router.get("/config")
async def get_ai_config(current_user: dict = Depends(get_current_user)):
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
    current_user: dict = Depends(get_current_user),
):
    return await generate_email(request, current_user)


@router.post("/enrich")
async def enrich(
    request: EnrichRequest,
    current_user: dict = Depends(get_current_user),
):
    return await enrich_lead(request, current_user)


@router.post("/analyze-reply")
async def analyze_reply(
    request: ClassifyRequest,
    current_user: dict = Depends(get_current_user),
):
    return await classify_reply(request, current_user)


# ── AI Prompts CRUD ──────────────────────────────────────────────────

@router.get("/prompts")
async def list_prompts(
    category: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
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
    current_user: dict = Depends(get_current_user),
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
    current_user: dict = Depends(get_current_user),
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
    current_user: dict = Depends(get_current_user),
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
async def get_ai_settings(current_user: dict = Depends(get_current_user)):
    await MongoDB.connect()
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("ai_settings")
    doc = await coll.find_one({"organization_id": org_id})
    if not doc:
        return {
            "provider": settings.ai_provider or "openai",
            "model": settings.ai_default_model or "gpt-4o",
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
    current_user: dict = Depends(get_current_user),
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
    current_user: dict = Depends(get_current_user),
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
    current_user: dict = Depends(get_current_user),
):
    url = data.get("url", "")
    prompt = f"Analyze this website URL and describe its business: {url}"
    content, err = await generate_text(prompt, max_tokens=300)
    if content:
        return {"analyzed": True, "summary": content, "url": url}
    return {"analyzed": True, "summary": f"Website at {url}", "url": url, "error": err}


# =============================================================================
# AI Provider Configuration CRUD
# =============================================================================

class AIProviderBase(BaseModel):
    name: str
    provider_type: str  # ollama, openai, anthropic, custom
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    is_active: bool = True
    is_default: bool = False


class AIProviderCreate(AIProviderBase):
    pass


class AIProviderUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


class AIProviderResponse(BaseModel):
    id: str
    name: str
    provider_type: str
    base_url: Optional[str] = None
    api_key_configured: bool = False
    is_active: bool
    is_default: bool
    models: list = []
    created_at: str
    updated_at: str


class TestProviderRequest(BaseModel):
    provider_type: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None


class FetchModelsRequest(BaseModel):
    provider_type: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None


def _mask_key(key: Optional[str]) -> str:
    if not key:
        return ""
    return "*" * 8 + key[-4:] if len(key) > 4 else "*" * 8


@router.get("/providers", response_model=list[AIProviderResponse])
async def list_providers(current_user: dict = Depends(get_current_user)):
    """List all AI providers for the organization."""
    await MongoDB.connect()
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("ai_providers")
    cursor = coll.find({"organization_id": org_id}).sort("created_at", -1)
    providers = []
    async for doc in cursor:
        providers.append(AIProviderResponse(
            id=str(doc["_id"]),
            name=doc.get("name", ""),
            provider_type=doc.get("provider_type", ""),
            base_url=doc.get("base_url"),
            api_key_configured=bool(doc.get("api_key")),
            is_active=doc.get("is_active", True),
            is_default=doc.get("is_default", False),
            models=doc.get("models", []),
            created_at=doc.get("created_at", ""),
            updated_at=doc.get("updated_at", ""),
        ))
    return providers


@router.post("/providers", response_model=AIProviderResponse)
async def create_provider(
    data: AIProviderCreate,
    current_user: dict = Depends(get_current_user),
):
    """Create a new AI provider."""
    await MongoDB.connect()
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("ai_providers")

    if data.is_default:
        await coll.update_many(
            {"organization_id": org_id, "is_default": True},
            {"$set": {"is_default": False}},
        )

    now = datetime.utcnow().isoformat()
    doc = {
        "organization_id": org_id,
        "name": data.name,
        "provider_type": data.provider_type,
        "base_url": data.base_url,
        "api_key": data.api_key,
        "is_active": data.is_active,
        "is_default": data.is_default,
        "models": [],
        "created_at": now,
        "updated_at": now,
    }
    result = await coll.insert_one(doc)
    doc["_id"] = result.inserted_id
    return AIProviderResponse(
        id=str(result.inserted_id),
        name=doc["name"],
        provider_type=doc["provider_type"],
        base_url=doc["base_url"],
        api_key_configured=bool(doc["api_key"]),
        is_active=doc["is_active"],
        is_default=doc["is_default"],
        models=[],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


@router.patch("/providers/{provider_id}", response_model=AIProviderResponse)
async def update_provider(
    provider_id: str,
    data: AIProviderUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update an AI provider (edit, toggle active/inactive)."""
    from bson import ObjectId
    await MongoDB.connect()
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("ai_providers")

    if data.is_default:
        await coll.update_many(
            {"organization_id": org_id, "is_default": True},
            {"$set": {"is_default": False}},
        )

    update = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    update["updated_at"] = datetime.utcnow().isoformat()
    result = await coll.update_one(
        {"_id": ObjectId(provider_id), "organization_id": org_id},
        {"$set": update},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Provider not found")

    doc = await coll.find_one({"_id": ObjectId(provider_id)})
    return AIProviderResponse(
        id=str(doc["_id"]),
        name=doc.get("name", ""),
        provider_type=doc.get("provider_type", ""),
        base_url=doc.get("base_url"),
        api_key_configured=bool(doc.get("api_key")),
        is_active=doc.get("is_active", True),
        is_default=doc.get("is_default", False),
        models=doc.get("models", []),
        created_at=doc.get("created_at", ""),
        updated_at=doc.get("updated_at", ""),
    )


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete an AI provider."""
    from bson import ObjectId
    await MongoDB.connect()
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("ai_providers")
    result = await coll.delete_one({"_id": ObjectId(provider_id), "organization_id": org_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Provider not found")
    return {"success": True}


@router.post("/providers/test")
async def test_provider(
    data: TestProviderRequest,
    current_user: dict = Depends(get_current_user),
):
    """Test AI provider connection."""
    import httpx
    try:
        if data.provider_type == "ollama":
            url = f"{data.base_url or 'http://localhost:11434'}/api/tags"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                ok = resp.status_code == 200
                models = []
                if ok:
                    models = [m.get("name", "") for m in resp.json().get("models", [])]
                return {"success": ok, "message": "Connected" if ok else "Connection failed", "models": models}

        elif data.provider_type == "openai":
            url = f"{data.base_url or 'https://api.openai.com/v1'}/models"
            headers = {"Authorization": f"Bearer {data.api_key}"} if data.api_key else {}
            async with httpx.AsyncClient(timeout=10, headers=headers) as client:
                resp = await client.get(url)
                ok = resp.status_code == 200
                models = [m.get("id", "") for m in resp.json().get("data", [])] if ok else []
                return {"success": ok, "message": "Connected" if ok else "Invalid API key or endpoint", "models": models}

        elif data.provider_type == "anthropic":
            url = f"{data.base_url or 'https://api.anthropic.com/v1'}/messages"
            headers = {
                "x-api-key": data.api_key or "",
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            payload = {"max_tokens": 1, "messages": [{"role": "user", "content": "test"}]}
            async with httpx.AsyncClient(timeout=10, headers=headers) as client:
                resp = await client.post(url, json=payload)
                ok = resp.status_code in (200, 400)
                return {"success": ok, "message": "Connected" if ok else "Invalid API key", "models": ["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"]}

        else:
            return {"success": False, "message": "Unknown provider type", "models": []}

    except Exception as e:
        return {"success": False, "message": str(e), "models": []}


@router.post("/providers/{provider_id}/models")
async def fetch_provider_models(
    provider_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Fetch available models for a provider and store them."""
    from bson import ObjectId
    await MongoDB.connect()
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("ai_providers")
    doc = await coll.find_one({"_id": ObjectId(provider_id), "organization_id": org_id})
    if not doc:
        raise HTTPException(404, "Provider not found")

    provider_type = doc.get("provider_type", "")
    base_url = doc.get("base_url")
    api_key = doc.get("api_key")

    try:
        import httpx
        models = []
        if provider_type == "ollama":
            url = f"{base_url or 'http://localhost:11434'}/api/tags"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    models = [{"name": m.get("name", ""), "provider": "ollama"} for m in resp.json().get("models", [])]
        elif provider_type == "openai":
            url = f"{base_url or 'https://api.openai.com/v1'}/models"
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            async with httpx.AsyncClient(timeout=10, headers=headers) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    models = [{"name": m.get("id", ""), "provider": "openai"} for m in resp.json().get("data", [])]
        elif provider_type == "anthropic":
            models = [
                {"name": "claude-3-5-sonnet-20241022", "provider": "anthropic"},
                {"name": "claude-3-haiku-20240307", "provider": "anthropic"},
                {"name": "claude-3-opus-20240229", "provider": "anthropic"},
            ]
        else:
            models = []

        await coll.update_one(
            {"_id": ObjectId(provider_id)},
            {"$set": {"models": models, "updated_at": datetime.utcnow().isoformat()}},
        )
        return {"success": True, "models": models, "count": len(models)}

    except Exception as e:
        return {"success": False, "message": str(e), "models": []}
