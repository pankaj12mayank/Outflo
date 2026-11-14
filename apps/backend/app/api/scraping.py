"""
Scraping API Endpoints (MongoDB)
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from typing import List, Optional
from pydantic import BaseModel

from app.middleware.auth import require_permission
from app.db.mongodb import MongoDB

router = APIRouter(prefix="/scraping", tags=["Scraping"])

_scraping_read = require_permission("scraping", "read")
_scraping_create = require_permission("scraping", "create")
_scraping_update = require_permission("scraping", "update")


class ScrapingJobResponse(BaseModel):
    id: str
    status: str = "pending"
    job_type: str
    total_items: int = 0


# ── Google Maps ──────────────────────────────────────────────────────

@router.post("/google-maps/search")
async def google_maps_search(
    data: dict,
    current_user: dict = Depends(_scraping_create),
):
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("scraping_jobs")
    doc = {
        "organization_id": org_id,
        "job_type": "google_maps_search",
        "status": "pending",
        "params": data,
        "created_at": datetime.utcnow().isoformat(),
    }
    result = await coll.insert_one(doc)
    return {"id": str(result.inserted_id), "status": "pending", "job_type": "google_maps_search"}


@router.post("/google-maps/crawl")
async def google_maps_crawl(
    data: dict,
    current_user: dict = Depends(_scraping_create),
):
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("scraping_jobs")
    doc = {
        "organization_id": org_id,
        "job_type": "google_maps_crawl",
        "status": "pending",
        "params": data,
        "created_at": datetime.utcnow().isoformat(),
    }
    result = await coll.insert_one(doc)
    return {"id": str(result.inserted_id), "status": "pending", "job_type": "google_maps_crawl"}


# ── Website ──────────────────────────────────────────────────────────

@router.post("/website/crawl")
async def website_crawl(
    data: dict,
    current_user: dict = Depends(_scraping_create),
):
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("scraping_jobs")
    doc = {
        "organization_id": org_id,
        "job_type": "website_crawl",
        "status": "pending",
        "params": data,
        "created_at": datetime.utcnow().isoformat(),
    }
    result = await coll.insert_one(doc)
    return {"id": str(result.inserted_id), "status": "pending", "job_type": "website_crawl"}


@router.post("/website/crawl/sync")
async def website_crawl_sync(
    data: dict,
    current_user: dict = Depends(_scraping_create),
):
    """Synchronously crawl a website and return flattened contact data."""
    from app.services.scraping import get_scraping_service

    url = data.get("url", "")
    if not url:
        raise HTTPException(400, "url is required")

    service = get_scraping_service()
    try:
        result = await service.crawl_website(
            url, crawl_contact_pages=bool(data.get("crawl_contact_pages", True))
        )
    except Exception as e:
        import traceback
        print("WEBSITE_CRAWL_SYNC_TRACEBACK:")
        traceback.print_exc()
        raise HTTPException(502, f"Crawl failed: {e}")

    payload = result.to_dict()
    raw = payload.get("raw_data") or {}
    emails = raw.get("emails") or []
    phones = raw.get("phones") or []
    social = raw.get("social_links") or {}
    title = raw.get("title") or payload.get("business_name") or ""
    pages = raw.get("pages_crawled") or ["Homepage"]

    return {
        "url": url,
        "website": url,
        "title": title,
        "business_name": payload.get("business_name") or title,
        "description": raw.get("description", ""),
        "emails": emails,
        "phones": phones,
        "phone": payload.get("phone") or (phones[0] if phones else ""),
        "whatsapp": payload.get("whatsapp") or raw.get("whatsapp") or "",
        "calendly": payload.get("calendly") or raw.get("calendly") or "",
        "has_contact_form": bool(payload.get("has_contact_form")),
        "has_cta": bool(payload.get("has_cta")),
        "social_links": social,
        "pages_crawled": pages,
        "forms_count": raw.get("forms_count", 0),
        "ctas_count": raw.get("ctas_count", 0),
        "data_quality_score": payload.get("data_quality_score", 0),
        "success": bool(payload.get("success")),
    }


# ── LinkedIn ─────────────────────────────────────────────────────────

@router.post("/linkedin/enrich")
async def linkedin_enrich(
    data: dict,
    current_user: dict = Depends(_scraping_create),
):
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("scraping_jobs")
    doc = {
        "organization_id": org_id,
        "job_type": "linkedin_enrich",
        "status": "pending",
        "params": data,
        "created_at": datetime.utcnow().isoformat(),
    }
    result = await coll.insert_one(doc)
    return {"id": str(result.inserted_id), "status": "pending", "job_type": "linkedin_enrich"}


@router.post("/linkedin/enrich/sync")
async def linkedin_enrich_sync(
    data: dict,
    current_user: dict = Depends(_scraping_create),
):
    """Synchronously enrich a LinkedIn profile URL with public data."""
    from app.services.scraping import get_scraping_service

    url = data.get("linkedin_url") or data.get("url", "")
    if not url:
        raise HTTPException(400, "linkedin_url is required")

    service = get_scraping_service()
    try:
        result = await service.enrich_linkedin(url)
    except Exception as e:
        raise HTTPException(502, f"Enrichment failed: {e}")

    payload = result.to_dict()
    return {
        "linkedin_url": url,
        "url": url,
        "name": payload.get("linkedin_name") or payload.get("business_name") or "",
        "title": payload.get("linkedin_title") or "",
        "company": payload.get("linkedin_company") or payload.get("business_name") or "",
        "location": payload.get("linkedin_location") or payload.get("city") or "",
        "email": payload.get("email") or "",
        "about": (payload.get("raw_data") or {}).get("about", ""),
        "enriched": bool(payload.get("success")),
        "success": bool(payload.get("success")),
        "error": payload.get("error_message"),
        "data_quality_score": payload.get("data_quality_score", 0),
    }


# ── CSV ──────────────────────────────────────────────────────────────

@router.post("/csv/parse")
async def csv_parse(
    file: UploadFile = File(...),
    current_user: dict = Depends(_scraping_create),
):
    content = await file.read()
    import csv, io
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    return {"total_rows": len(rows), "columns": reader.fieldnames or [], "preview": rows[:5]}


@router.post("/csv/import")
async def csv_import(
    file: UploadFile = File(...),
    current_user: dict = Depends(_scraping_create),
):
    content = await file.read()
    import csv, io
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    org_id = current_user.get("organization_id")
    leads_coll = MongoDB.get_collection("leads")
    imported = 0
    for row in rows:
        row["organization_id"] = org_id
        row["created_at"] = datetime.utcnow().isoformat()
        await leads_coll.insert_one(row)
        imported += 1
    return {"imported": imported, "total": len(rows)}


# ── Jobs CRUD ───────────────────────────────────────────────────────

@router.get("/jobs")
async def list_jobs(
    status: Optional[str] = None,
    limit: int = 100,
    current_user: dict = Depends(_scraping_read),
):
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("scraping_jobs")
    query = {"organization_id": org_id}
    if status:
        query["status"] = status
    cursor = coll.find(query).sort("_id", -1).limit(max(1, min(limit, 500)))
    jobs = []
    async for doc in cursor:
        jobs.append({
            "id": str(doc["_id"]),
            "status": doc.get("status"),
            "job_type": doc.get("job_type"),
            "params": doc.get("params") or {},
            "total_items": doc.get("total_items", 0),
            "results_count": doc.get("results_count", 0),
            "created_at": doc.get("created_at"),
            "completed_at": doc.get("completed_at"),
            "error": doc.get("error"),
        })
    return jobs


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    current_user: dict = Depends(_scraping_read),
):
    from bson import ObjectId
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("scraping_jobs")
    doc = await coll.find_one({"_id": ObjectId(job_id), "organization_id": org_id})
    if not doc:
        raise HTTPException(404, "Job not found")
    return {
        "id": str(doc["_id"]),
        "status": doc.get("status"),
        "job_type": doc.get("job_type"),
        "params": doc.get("params"),
        "total_items": doc.get("total_items", 0),
        "results_count": doc.get("results_count", 0),
        "created_at": doc.get("created_at"),
        "started_at": doc.get("started_at"),
        "completed_at": doc.get("completed_at"),
        "error": doc.get("error"),
    }


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    current_user: dict = Depends(_scraping_update),
):
    from bson import ObjectId
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("scraping_jobs")
    result = await coll.update_one(
        {"_id": ObjectId(job_id), "organization_id": org_id},
        {"$set": {"status": "cancelled"}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Job not found")
    return {"success": True}


@router.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: str,
    current_user: dict = Depends(_scraping_update),
):
    from bson import ObjectId
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("scraping_jobs")
    result = await coll.update_one(
        {"_id": ObjectId(job_id), "organization_id": org_id},
        {"$set": {"status": "pending"}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Job not found")
    return {"success": True}


@router.get("/jobs/{job_id}/results")
async def get_job_results(
    job_id: str,
    skip: int = 0,
    limit: int = 100,
    current_user: dict = Depends(_scraping_read),
):
    from bson import ObjectId
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("scraping_results")
    cursor = coll.find({"job_id": job_id, "organization_id": org_id}).skip(
        max(0, skip)
    ).limit(max(1, min(limit, 500)))
    results = []
    async for doc in cursor:
        results.append({
            "id": str(doc["_id"]),
            "data": doc.get("data"),
        })
    return results


# ── Bulk Enrich ──────────────────────────────────────────────────────

@router.post("/bulk/enrich")
async def bulk_enrich(
    data: dict,
    current_user: dict = Depends(_scraping_create),
):
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("scraping_jobs")
    doc = {
        "organization_id": org_id,
        "job_type": "bulk_enrich",
        "status": "pending",
        "params": data,
        "created_at": datetime.utcnow().isoformat(),
    }
    result = await coll.insert_one(doc)
    return {"id": str(result.inserted_id), "status": "pending", "job_type": "bulk_enrich"}


# ── Stats ────────────────────────────────────────────────────────────

@router.get("/stats")
async def scraping_stats(
    current_user: dict = Depends(_scraping_read),
):
    org_id = current_user.get("organization_id")
    coll = MongoDB.get_collection("scraping_jobs")
    total = await coll.count_documents({"organization_id": org_id})
    running = await coll.count_documents({"organization_id": org_id, "status": "running"})
    completed = await coll.count_documents({"organization_id": org_id, "status": "completed"})
    failed = await coll.count_documents({"organization_id": org_id, "status": "failed"})
    return {
        "total_jobs": total,
        "running": running,
        "completed": completed,
        "failed": failed,
    }