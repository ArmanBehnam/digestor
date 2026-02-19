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
from sqlalchemy import select, func

from api.dependencies import get_db, get_current_user
from db.models import Ticket, User

logger = structlog.get_logger()
router = APIRouter()


class CreateTicketRequest(BaseModel):
    subject: str
    description: str
    category: Optional[str] = "other"  # bug, feature, question, other
    priority: Optional[str] = "medium"  # low, medium, high, urgent


class UpdateTicketRequest(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    resolution: Optional[str] = None


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

    ticket = Ticket(
        user_id=user.id,
        subject=req.subject,
        description=req.description,
        category=req.category,
        priority=req.priority,
        status="open",
    )
    db.add(ticket)
    await db.flush()

    # Send email notification to admins
    from services.email_service import notify_new_ticket
    await notify_new_ticket(ticket, user, db)

    logger.info("ticket_created", ticket_id=str(ticket.id), subject=req.subject)
    return {
        "id": str(ticket.id),
        "subject": ticket.subject,
        "status": "open",
        "message": "Ticket created successfully",
    }


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
        stmt = stmt.where(Ticket.status == status)

    stmt = stmt.order_by(Ticket.created_at.desc())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(stmt)
    tickets = result.scalars().all()

    return {
        "tickets": [
            {
                "id": str(t.id),
                "subject": t.subject,
                "category": t.category,
                "priority": t.priority,
                "status": t.status,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tickets
        ],
    }


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
        ticket.status = req.status
        if req.status == "resolved":
            ticket.resolved_at = datetime.utcnow()
    if req.resolution:
        ticket.resolution = req.resolution
    if req.assigned_to:
        ticket.assigned_to = uuid.UUID(req.assigned_to)

    await db.flush()
    return {"message": "Ticket updated", "id": str(ticket.id)}
