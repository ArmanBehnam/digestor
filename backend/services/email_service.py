"""
AWS SES email service for notifications.
Replaces Supabase send-ticket-notification edge function.
"""

import os
import structlog
import boto3
from botocore.exceptions import ClientError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = structlog.get_logger()

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
SES_FROM_EMAIL = os.getenv("SES_FROM_EMAIL", "noreply@digestor.com")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@digestor.com")

_ses_client = None


def _get_ses():
    global _ses_client
    if _ses_client is None:
        _ses_client = boto3.client("ses", region_name=AWS_REGION)
    return _ses_client


async def send_email(to: str, subject: str, body_html: str, body_text: str = ""):
    """Send an email via AWS SES."""
    ses = _get_ses()

    try:
        ses.send_email(
            Source=SES_FROM_EMAIL,
            Destination={"ToAddresses": [to]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Html": {"Data": body_html, "Charset": "UTF-8"},
                    "Text": {"Data": body_text or subject, "Charset": "UTF-8"},
                },
            },
        )
        logger.info("email_sent", to=to, subject=subject)
    except ClientError as e:
        logger.error("email_send_failed", to=to, subject=subject, error=str(e))


async def notify_new_ticket(ticket, user, db: AsyncSession):
    """Notify admins about a new support ticket."""
    await send_email(
        to=ADMIN_EMAIL,
        subject=f"[Digestor] New Ticket: {ticket.subject}",
        body_html=f"""
        <h2>New Support Ticket</h2>
        <p><strong>From:</strong> {user.full_name} ({user.email})</p>
        <p><strong>Subject:</strong> {ticket.subject}</p>
        <p><strong>Category:</strong> {ticket.category}</p>
        <p><strong>Priority:</strong> {ticket.priority}</p>
        <hr>
        <p>{ticket.description}</p>
        """,
    )


async def notify_supervisors_new_submission(project, db: AsyncSession):
    """Notify supervisors about a new project submission."""
    from db.models import User

    # Find all supervisors
    stmt = select(User).where(User.role.in_(["supervisor", "admin"]), User.is_active == True)
    result = await db.execute(stmt)
    supervisors = result.scalars().all()

    for supervisor in supervisors:
        await send_email(
            to=supervisor.email,
            subject=f"[Digestor] Project Submitted for Review: {project.name}",
            body_html=f"""
            <h2>Project Submitted for Review</h2>
            <p><strong>Project:</strong> {project.name}</p>
            <p><strong>Description:</strong> {project.description or 'N/A'}</p>
            <p>Please log in to review and approve this project.</p>
            """,
        )


async def notify_project_decision(project, approved: bool, remarks: str, db: AsyncSession):
    """Notify project owner about approval/rejection."""
    from db.models import User

    owner_stmt = select(User).where(User.id == project.owner_id)
    owner = (await db.execute(owner_stmt)).scalar_one_or_none()

    if not owner:
        return

    status = "Approved" if approved else "Rejected"
    await send_email(
        to=owner.email,
        subject=f"[Digestor] Project {status}: {project.name}",
        body_html=f"""
        <h2>Project {status}</h2>
        <p><strong>Project:</strong> {project.name}</p>
        <p><strong>Status:</strong> {status}</p>
        {"<p><strong>Remarks:</strong> " + remarks + "</p>" if remarks else ""}
        <p>Log in to view details.</p>
        """,
    )
