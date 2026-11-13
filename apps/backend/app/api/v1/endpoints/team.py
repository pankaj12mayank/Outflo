"""
Team API Endpoints (MongoDB)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from pydantic import BaseModel, EmailStr
from datetime import datetime
from app.middleware.rbac import require_permissions
from app.repositories.mongo_repositories import TeamInvitationRepository

router = APIRouter(prefix="/team", tags=["Team"])


class TeamMemberResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    role: str
    is_active: bool = True
    created_at: Optional[str] = None


class TeamInvitationResponse(BaseModel):
    id: str
    email: EmailStr
    role: str
    status: str
    invited_by: str
    created_at: Optional[str] = None
    temporary_password: Optional[str] = None


def _invitation_response(doc: dict) -> dict:
    created = doc.get("created_at")
    return {
        "id": str(doc.get("_id") or doc.get("id") or ""),
        "email": doc.get("email"),
        "role": _normalize_team_role(doc.get("role")) if doc.get("role") else "team_member",
        "status": doc.get("status") or "pending",
        "invited_by": doc.get("invited_by") or "",
        "created_at": created.isoformat() if hasattr(created, "isoformat") else created,
        "temporary_password": doc.get("temporary_password"),
    }


def _normalize_team_role(role: Optional[str]) -> str:
    if role in ("member", "admin"):
        return "team_member" if role == "member" else "organization_admin"
    return role or "team_member"


def _member_response(doc: dict) -> dict:
    created = doc.get("created_at")
    return {
        "id": str(doc.get("_id") or doc.get("id") or ""),
        "email": doc.get("email"),
        "full_name": doc.get("full_name"),
        "role": _normalize_team_role(doc.get("role")),
        "is_active": doc.get("is_active", True) is not False,
        "created_at": created.isoformat() if hasattr(created, "isoformat") else created,
    }


@router.get("/members", response_model=List[TeamMemberResponse])
async def list_team_members(
    current_user: dict = Depends(require_permissions(["teams:read"])),
):
    from app.db.mongodb import MongoDB

    await MongoDB.connect()
    org_id = current_user.get("organization_id")
    docs = await MongoDB.get_collection("users").find(
        {"organization_id": org_id, "is_active": {"$ne": False}, "deleted_at": None}
    ).sort("created_at", 1).to_list(length=500)
    return [_member_response(doc) for doc in docs]


@router.post("/members", response_model=TeamMemberResponse, status_code=status.HTTP_201_CREATED)
async def add_team_member(
    member_in: dict,
    current_user: dict = Depends(require_permissions(["teams:create"])),
):
    from app.db.mongodb import MongoDB
    from app.core.security import get_password_hash
    from app.core.config import settings

    org_id = current_user.get("organization_id")
    email = str(member_in.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is required")

    users_coll = MongoDB.get_collection("users")
    if await users_coll.find_one({"email": email}):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    now = datetime.utcnow()
    role = "organization_admin" if member_in.get("role") in ("admin", "organization_admin") else "team_member"
    password = str(member_in.get("password") or getattr(settings, "team_member_default_password", "Test@1234"))
    doc = {
        "email": email,
        "password_hash": await get_password_hash(password),
        "full_name": member_in.get("full_name") or email.split("@")[0],
        "role": role,
        "organization_id": org_id,
        "is_active": True,
        "is_email_verified": False,
        "created_at": now,
        "updated_at": now,
    }
    result = await users_coll.insert_one(doc)
    await MongoDB.get_collection("memberships").insert_one({
        "user_id": str(result.inserted_id),
        "organization_id": org_id,
        "role": role,
        "status": "active",
        "accepted_at": now,
        "created_at": now,
    })
    doc["_id"] = result.inserted_id
    return _member_response(doc)


@router.api_route("/members/{member_id}", methods=["PUT", "PATCH"], response_model=TeamMemberResponse)
async def update_team_member(
    member_id: str,
    member_in: dict,
    current_user: dict = Depends(require_permissions(["teams:update"])),
):
    from bson import ObjectId
    from app.db.mongodb import MongoDB

    org_id = current_user.get("organization_id")
    try:
        oid = ObjectId(member_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    update_data = {k: v for k, v in member_in.items() if v is not None}
    if "role" in update_data:
        update_data["role"] = _normalize_team_role(update_data["role"])
    update_data["updated_at"] = datetime.utcnow()

    users_coll = MongoDB.get_collection("users")
    result = await users_coll.update_one(
        {"_id": oid, "organization_id": org_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if "role" in update_data:
        await MongoDB.get_collection("memberships").update_many(
            {"user_id": member_id, "organization_id": org_id},
            {"$set": {"role": update_data["role"]}},
        )

    doc = await users_coll.find_one({"_id": oid})
    return _member_response(doc)


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    member_id: str,
    current_user: dict = Depends(require_permissions(["teams:delete"])),
):
    from bson import ObjectId
    from app.db.mongodb import MongoDB

    current_id = str(current_user.get("sub") or current_user.get("id") or "")
    if member_id == current_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot remove yourself")

    org_id = current_user.get("organization_id")
    try:
        oid = ObjectId(member_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    now = datetime.utcnow()
    result = await MongoDB.get_collection("users").update_one(
        {"_id": oid, "organization_id": org_id},
        {"$set": {"is_active": False, "deleted_at": now, "updated_at": now}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    await MongoDB.get_collection("memberships").update_many(
        {"user_id": member_id, "organization_id": org_id},
        {"$set": {"status": "removed", "updated_at": now}},
    )
    return None


@router.get("/invitations", response_model=List[TeamInvitationResponse])
async def list_pending_invitations(
    current_user: dict = Depends(require_permissions(["teams:read"])),
):
    from app.db.mongodb import MongoDB

    await MongoDB.connect()
    org_id = current_user.get("organization_id")
    invite_repo = TeamInvitationRepository(org_id)
    invitations = await invite_repo.get_pending_invitations()
    return [_invitation_response(inv) for inv in invitations]


@router.post("/invitations", response_model=TeamInvitationResponse, status_code=status.HTTP_201_CREATED)
async def invite_team_member(
    invitation_in: dict,
    current_user: dict = Depends(require_permissions(["teams:create"])),
):
    from app.db.mongodb import MongoDB
    from app.services.plan_service import PlanService, SubscriptionService

    org_id = current_user.get("organization_id")
    sub = await SubscriptionService.get_subscription(org_id)
    plan = None
    if sub and sub.get("plan_id"):
        plan = await PlanService.get_plan(sub["plan_id"])
    if not plan:
        plan = await PlanService.get_default_plan()
    team_limit = PlanService.get_team_member_limit(plan) if plan else 1

    active_members = await MongoDB.get_collection("users").count_documents(
        {
            "organization_id": org_id,
            "role": {"$in": ["team_member", "member"]},
            "is_active": {"$ne": False},
            "deleted_at": None,
        }
    )
    invite_repo = TeamInvitationRepository(org_id)
    pending = await invite_repo.get_pending_invitations()
    pending_count = sum(
        1 for inv in pending if inv.get("email") and inv.get("status") == "pending"
    )
    if active_members + pending_count >= team_limit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Team member limit reached ({team_limit}) for your current plan. Upgrade to add more.",
        )
    invite_role = invitation_in.get("role", "member")
    if invite_role == "team_member":
        invite_role = "member"
    email = str(invitation_in.get("email") or "").lower().strip()
    invitation_data = {
        "email": email,
        "role": invite_role,
        "status": "pending",
        "invited_by": current_user.get("email"),
        "organization_id": org_id,
    }

    # Create a real login account for the invited member so they can sign in
    # immediately with the temporary password returned below. Existing users
    # simply receive the invitation and keep their current credentials.
    from app.core.security import get_password_hash
    from app.core.config import settings

    temp_password: Optional[str] = None
    users_coll = MongoDB.get_collection("users")
    existing_user = await users_coll.find_one({"email": email})
    if not existing_user and email:
        temp_password = getattr(settings, "team_member_default_password", "Test@1234")
        now = datetime.utcnow()
        user_role = "organization_admin" if invite_role == "admin" else "team_member"
        user_doc = {
            "email": email,
            "password_hash": await get_password_hash(temp_password),
            "full_name": invitation_in.get("full_name") or email.split("@")[0],
            "role": user_role,
            "organization_id": org_id,
            "is_active": True,
            "is_email_verified": False,
            "created_at": now,
            "updated_at": now,
        }
        try:
            user_result = await users_coll.insert_one(user_doc)
            await MongoDB.get_collection("memberships").insert_one({
                "user_id": str(user_result.inserted_id),
                "organization_id": org_id,
                "role": user_role,
                "status": "active",
                "accepted_at": now,
                "created_at": now,
            })
            invitation_data["status"] = "accepted"
            invitation_data["accepted_at"] = now
        except Exception as exc:
            if "duplicate key" not in str(exc).lower() and "E11000" not in str(exc):
                raise
            temp_password = None

    invitation = await invite_repo.create(invitation_data)
    invitation["temporary_password"] = temp_password
    return _invitation_response(invitation)


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_invitation(
    invitation_id: str,
    current_user: dict = Depends(require_permissions(["teams:delete"])),
):
    org_id = current_user.get("organization_id")
    invite_repo = TeamInvitationRepository(org_id)
    result = await invite_repo.delete(invitation_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    return None


@router.post("/invitations/{invitation_id}/resend", response_model=TeamInvitationResponse)
async def resend_invitation(
    invitation_id: str,
    current_user: dict = Depends(require_permissions(["teams:update"])),
):
    org_id = current_user.get("organization_id")
    invite_repo = TeamInvitationRepository(org_id)
    invitation = await invite_repo.update(invitation_id, {"resent_at": datetime.utcnow()})
    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    return _invitation_response(invitation)