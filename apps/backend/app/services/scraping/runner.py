"""
Outflo - Scraping Job Runner

Background execution for scraping jobs queued by the API layer.

Jobs sit in the `scraping_jobs` collection with status "pending". This runner
claims them atomically (pending -> running), executes the real scraper, and
writes each extracted record into `scraping_results`. The job document is
then marked completed/failed with counts and timings.

Executed by PollingService.check_scraping_jobs every 5 seconds.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from bson import ObjectId
from pymongo import ReturnDocument

from app.db.mongodb import MongoDB

logger = logging.getLogger(__name__)

JOB_TIMEOUT_SECONDS = 240
STALE_RUNNING_SECONDS = 600
MAX_BULK_LEADS = 20


def _serialize_result(result: Any) -> Dict[str, Any]:
    """Convert a ScrapeResult (or plain dict) into a storable payload."""
    try:
        if hasattr(result, "to_dict"):
            return result.to_dict()
        if isinstance(result, dict):
            return result
        return {"value": str(result)}
    except Exception:
        return {"value": str(result)}


async def requeue_stale_jobs() -> int:
    """Reset jobs stuck in 'running' (crashed worker) back to 'pending'."""
    coll = MongoDB.get_collection("scraping_jobs")
    cutoff = datetime.utcnow() - timedelta(seconds=STALE_RUNNING_SECONDS)
    res = await coll.update_many(
        {
            "status": "running",
            "$or": [
                {"started_at": {"$exists": False}},
                {"started_at": {"$lt": cutoff}},
            ],
        },
        {"$set": {"status": "pending"}},
    )
    if res.modified_count:
        logger.info("Requeued %d stale scraping jobs", res.modified_count)
    return res.modified_count


async def run_pending_scraping_jobs(limit: int = 1) -> int:
    """Claim and execute up to `limit` pending scraping jobs.

    Claiming is atomic (find_one_and_update pending -> running), so this is
    the single execution path for a job — no task-creation races.
    """
    processed = 0
    for _ in range(limit):
        coll = MongoDB.get_collection("scraping_jobs")
        job = await coll.find_one_and_update(
            {"status": "pending"},
            {
                "$set": {"status": "running", "started_at": datetime.utcnow()},
                "$unset": {"error": ""},
            },
            sort=[("_id", 1)],
            return_document=ReturnDocument.AFTER,
        )
        if not job:
            break
        processed += 1
        await _execute_job(job)
    return processed


async def _execute_job(job: Dict[str, Any]) -> None:
    coll = MongoDB.get_collection("scraping_jobs")
    results_coll = MongoDB.get_collection("scraping_results")
    job_id = job["_id"]
    job_id_str = str(job_id)
    params = job.get("params") or {}

    try:
        results = await asyncio.wait_for(
            _dispatch(job.get("job_type"), params, job.get("organization_id")),
            timeout=JOB_TIMEOUT_SECONDS,
        )
    except Exception as e:
        logger.error("Scraping job %s failed: %s", job_id_str, e)
        await coll.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "status": "failed",
                    "completed_at": datetime.utcnow(),
                    "error": str(e)[:500],
                }
            },
        )
        return

    if results:
        docs = [
            {
                "job_id": job_id_str,
                "organization_id": job.get("organization_id"),
                "data": item,
                "created_at": datetime.utcnow(),
            }
            for item in results
        ]
        await results_coll.insert_many(docs)

    await coll.update_one(
        {"_id": job_id},
        {
            "$set": {
                "status": "completed",
                "completed_at": datetime.utcnow(),
                "total_items": len(results),
                "results_count": len(results),
            }
        },
    )
    logger.info("Scraping job %s completed with %d result(s)", job_id_str, len(results))


async def _dispatch(job_type: str, params: Dict[str, Any], org_id: Any) -> List[Dict[str, Any]]:
    """Run the real scraper for a job type and return result dicts."""
    # Imported lazily: keeps API import path light and avoids cycles.
    from app.services.scraping import get_scraping_service

    service = get_scraping_service()

    if job_type == "google_maps_search":
        keyword = (params.get("keyword") or params.get("query") or "").strip()
        if not keyword:
            raise ValueError("keyword is required")
        location = params.get("location") or ""
        limit = int(params.get("limit") or 20)
        results = await service.search_google_maps(keyword, location, limit)
        return [_serialize_result(r) for r in results]

    if job_type == "google_maps_crawl":
        url = params.get("url")
        if not url:
            raise ValueError("url is required")
        result = await service.scrape_google_maps_place(url)
        return [_serialize_result(result)]

    if job_type == "website_crawl":
        url = params.get("url")
        if not url:
            raise ValueError("url is required")
        result = await service.crawl_website(
            url, crawl_contact_pages=bool(params.get("crawl_contact_pages", True))
        )
        return [_serialize_result(result)]

    if job_type == "linkedin_enrich":
        url = params.get("linkedin_url") or params.get("url")
        if not url:
            raise ValueError("linkedin_url is required")
        result = await service.enrich_linkedin(url)
        return [_serialize_result(result)]

    if job_type == "bulk_enrich":
        return await _bulk_enrich(params, org_id)

    raise ValueError(f"Unknown job_type: {job_type}")


async def _bulk_enrich(params: Dict[str, Any], org_id: Any) -> List[Dict[str, Any]]:
    """Enrich up to MAX_BULK_LEADS leads that have a website."""
    from app.services.scraping import get_scraping_service

    ids = params.get("lead_ids") or []
    leads_coll = MongoDB.get_collection("leads")

    query: Dict[str, Any] = {"organization_id": org_id}
    if ids:
        oid_list, str_ids = [], []
        for lead_id in ids[:MAX_BULK_LEADS]:
            try:
                oid_list.append(ObjectId(str(lead_id)))
            except Exception:
                str_ids.append(str(lead_id))
        conditions = []
        if oid_list:
            conditions.append({"_id": {"$in": oid_list}})
        if str_ids:
            conditions.append({"_id": {"$in": str_ids}})
        if conditions:
            query["$or"] = conditions
    else:
        query["website"] = {"$ne": None}

    leads = await leads_coll.find(query).limit(MAX_BULK_LEADS).to_list(length=MAX_BULK_LEADS)

    service = get_scraping_service()
    results: List[Dict[str, Any]] = []
    for lead in leads:
        site = lead.get("website")
        if not site:
            continue
        try:
            result = await service.crawl_website(site)
            payload = _serialize_result(result)
            payload["lead_id"] = str(lead.get("_id"))
            payload["lead_email"] = lead.get("email")
            results.append(payload)
        except Exception as e:
            logger.warning("bulk enrich failed for lead %s: %s", lead.get("_id"), e)
    return results
