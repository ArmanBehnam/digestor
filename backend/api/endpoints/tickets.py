"""
Ticket system endpoints - replaces Supabase send-ticket-notification.
"""

import uuid
import structlog
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.dependencies import get_db, get_current_user
from db.models import Ticket, User

logger = structlog.get_logger()
router = APIRouter()


class CreateTicketRequest(BaseModel):
    # Accept both frontend names (title/type) and backend names (subject/category)
    title: Optional[str] = None
    subject: Optional[str] = None
    description: str
    type: Optional[str] = None
    category: Optional[str] = "other"  # bug, feature, question, other
    priority: Optional[str] = "medium"  # low, medium, high, urgent


class UpdateTicketRequest(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    resolution: Optional[str] = None
    developer_notes: Optional[str] = None


@router.post("/tickets")
async def create_ticket(
    req: CreateTicketRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new support ticket."""
    user_stmt = select(User).where(User.cognito_sub == current_user["sub"])
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Accept either title or subject, type or category
    ticket_subject = req.title or req.subject or "Untitled"
    ticket_category = req.type or req.category or "other"

    ticket = Ticket(
        user_id=user.id,
        subject=ticket_subject,
        description=req.description,
        category=ticket_category,
        priority=req.priority,
        status="open",
    )
    db.add(ticket)
    await db.flush()

    # Send email notification to admins
    from services.email_service import notify_new_ticket
    await notify_new_ticket(ticket, user, db)

    logger.info("ticket_created", ticket_id=str(ticket.id), subject=ticket_subject)
    return {
        "id": str(ticket.id),
        "title": ticket.subject,
        "status": "submitted",
        "message": "Ticket created successfully",
    }


@router.get("/tickets/mine")
async def list_my_tickets(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List current user's own tickets."""
    user_stmt = select(User).where(User.cognito_sub == current_user["sub"])
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    stmt = (
        select(Ticket)
        .where(Ticket.user_id == user.id)
        .order_by(Ticket.created_at.desc())
    )
    result = await db.execute(stmt)
    tickets = result.scalars().all()

    status_to_frontend = {"open": "submitted"}

    return [
        {
            "id": str(t.id),
            "title": t.subject,
            "description": t.description or "",
            "type": t.category or "other",
            "status": status_to_frontend.get(t.status, t.status),
            "priority": t.priority or "medium",
            "submitted_by_user_id": str(t.user_id),
            "submitted_by_email": user.email,
            "submitted_by_name": user.full_name,
            "developer_notes": t.resolution,
            "assigned_to": str(t.assigned_to) if t.assigned_to else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
            "screenshot_url": None,
            "project_reference": None,
        }
        for t in tickets
    ]


@router.get("/tickets")
async def list_tickets(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List tickets (own tickets for engineer, all for admin)."""
    user_stmt = select(User).where(User.cognito_sub == current_user["sub"])
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user_groups = current_user.get("cognito:groups", [])
    stmt = select(Ticket)

    # Engineers see only their own tickets, admins see all
    if "admin" not in user_groups:
        stmt = stmt.where(Ticket.user_id == user.id)

    if status:
        # Map frontend status names to backend
        status_map = {"submitted": "open"}
        db_status = status_map.get(status, status)
        stmt = stmt.where(Ticket.status == db_status)

    stmt = stmt.order_by(Ticket.created_at.desc())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(stmt)
    tickets = result.scalars().all()

    # Build user lookup for submitted_by info
    user_ids = {t.user_id for t in tickets}
    user_lookup = {}
    if user_ids:
        user_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        for u in user_result.scalars().all():
            user_lookup[u.id] = u

    # Map backend status to frontend status
    status_to_frontend = {"open": "submitted"}

    # Return flat array matching frontend TicketData interface
    return [
        {
            "id": str(t.id),
            "title": t.subject,
            "description": t.description or "",
            "type": t.category or "other",
            "status": status_to_frontend.get(t.status, t.status),
            "priority": t.priority or "medium",
            "submitted_by_user_id": str(t.user_id),
            "submitted_by_email": user_lookup.get(t.user_id, None).email if user_lookup.get(t.user_id) else "",
            "submitted_by_name": user_lookup.get(t.user_id, None).full_name if user_lookup.get(t.user_id) else None,
            "developer_notes": t.resolution,
            "assigned_to": str(t.assigned_to) if t.assigned_to else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
            "screenshot_url": None,
            "project_reference": None,
        }
        for t in tickets
    ]


@router.put("/tickets/{ticket_id}")
async def update_ticket(
    ticket_id: str,
    req: UpdateTicketRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a ticket (admin only for status/assignment)."""
    stmt = select(Ticket).where(Ticket.id == uuid.UUID(ticket_id))
    ticket = (await db.execute(stmt)).scalar_one_or_none()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if req.status:
        # Map frontend status names to backend
        status_map = {"submitted": "open"}
        db_status = status_map.get(req.status, req.status)
        ticket.status = db_status
        if db_status == "resolved":
            ticket.resolved_at = datetime.utcnow()
    if req.resolution:
        ticket.resolution = req.resolution
    if req.developer_notes is not None:
        ticket.resolution = req.developer_notes
    if req.assigned_to:
        ticket.assigned_to = uuid.UUID(req.assigned_to)

    await db.flush()
    return {"message": "Ticket updated", "id": str(ticket.id)}
