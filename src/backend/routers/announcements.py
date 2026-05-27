"""
Announcement endpoints for the High School Management System API
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementPayload(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    message: str = Field(min_length=5, max_length=1000)
    expires_at: str
    starts_at: Optional[str] = None


def parse_iso_datetime(value: Optional[str], field_name: str) -> Optional[datetime]:
    if value is None:
        return None

    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return parsed
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}. Use ISO-8601 format."
        ) from exc


def normalize_announcement(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": doc.get("_id"),
        "title": doc.get("title", ""),
        "message": doc.get("message", ""),
        "starts_at": doc.get("starts_at"),
        "expires_at": doc.get("expires_at"),
        "created_by": doc.get("created_by", ""),
        "updated_at": doc.get("updated_at")
    }


def require_teacher(teacher_username: Optional[str]) -> Dict[str, Any]:
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


@router.get("", response_model=List[Dict[str, Any]])
def list_active_announcements() -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    active: List[Dict[str, Any]] = []

    for doc in announcements_collection.find({}).sort("expires_at", 1):
        starts_at = parse_iso_datetime(doc.get("starts_at"), "starts_at")
        expires_at = parse_iso_datetime(doc.get("expires_at"), "expires_at")

        if not expires_at:
            continue
        if starts_at and starts_at > now:
            continue
        if expires_at < now:
            continue

        active.append(normalize_announcement(doc))

    return active


@router.get("/manage", response_model=List[Dict[str, Any]])
def list_all_announcements_for_management(
    teacher_username: Optional[str] = Query(None)
) -> List[Dict[str, Any]]:
    require_teacher(teacher_username)
    announcements = announcements_collection.find({}).sort("expires_at", 1)
    return [normalize_announcement(doc) for doc in announcements]


@router.post("", response_model=Dict[str, Any])
def create_announcement(
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    teacher = require_teacher(teacher_username)

    title = payload.title.strip()
    message = payload.message.strip()

    if not title or not message:
        raise HTTPException(status_code=400, detail="title and message cannot be empty")

    starts_at_dt = parse_iso_datetime(payload.starts_at, "starts_at")
    expires_at_dt = parse_iso_datetime(payload.expires_at, "expires_at")

    if not expires_at_dt:
        raise HTTPException(status_code=400, detail="expires_at is required")

    if starts_at_dt and starts_at_dt >= expires_at_dt:
        raise HTTPException(
            status_code=400,
            detail="starts_at must be earlier than expires_at"
        )

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    announcement_id = str(uuid4())

    record = {
        "_id": announcement_id,
        "title": title,
        "message": message,
        "starts_at": starts_at_dt.isoformat().replace("+00:00", "Z") if starts_at_dt else None,
        "expires_at": expires_at_dt.isoformat().replace("+00:00", "Z"),
        "created_by": teacher["username"],
        "updated_at": now_iso
    }

    announcements_collection.insert_one(record)
    return normalize_announcement(record)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    require_teacher(teacher_username)

    title = payload.title.strip()
    message = payload.message.strip()

    if not title or not message:
        raise HTTPException(status_code=400, detail="title and message cannot be empty")

    existing = announcements_collection.find_one({"_id": announcement_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    starts_at_dt = parse_iso_datetime(payload.starts_at, "starts_at")
    expires_at_dt = parse_iso_datetime(payload.expires_at, "expires_at")

    if not expires_at_dt:
        raise HTTPException(status_code=400, detail="expires_at is required")

    if starts_at_dt and starts_at_dt >= expires_at_dt:
        raise HTTPException(
            status_code=400,
            detail="starts_at must be earlier than expires_at"
        )

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    updates = {
        "title": title,
        "message": message,
        "starts_at": starts_at_dt.isoformat().replace("+00:00", "Z") if starts_at_dt else None,
        "expires_at": expires_at_dt.isoformat().replace("+00:00", "Z"),
        "updated_at": now_iso
    }

    announcements_collection.update_one(
        {"_id": announcement_id},
        {"$set": updates}
    )

    updated = announcements_collection.find_one({"_id": announcement_id})
    return normalize_announcement(updated)


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    require_teacher(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted successfully"}
