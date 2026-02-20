"""
Digestor Unified - SQLAlchemy ORM Models
Maps to AWS RDS PostgreSQL schema.
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime,
    ForeignKey, JSON, Enum as SAEnum, Index, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class User(Base):
    """User profile synced with Cognito. Cognito is source of truth for auth."""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cognito_sub = Column(String(128), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(String(50), nullable=False, default="engineer")  # engineer, supervisor, admin
    organization = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    projects = relationship("Project", foreign_keys="[Project.owner_id]", back_populates="owner")
    feedback = relationship("UserFeedback", back_populates="user")
    tickets = relationship("Ticket", foreign_keys="[Ticket.user_id]", back_populates="user")


class Project(Base):
    """A processing project containing one or more documents."""
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status = Column(
        String(50), nullable=False, default="draft"
    )  # draft, processing, completed, submitted, approved, rejected
    approval_status = Column(String(50), nullable=True)  # pending, approved, rejected
    version = Column(Integer, default=1)
    notes = Column(Text, nullable=True)
    files_metadata = Column(JSONB, nullable=True)  # [{name, path, size}]
    pending_snapshot_json = Column(JSONB, nullable=True)  # Snapshot for supervisor review
    pending_snapshot_html = Column(Text, nullable=True)  # HTML snapshot
    assigned_supervisor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    review_note = Column(Text, nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    owner = relationship("User", foreign_keys=[owner_id], back_populates="projects")
    approver = relationship("User", foreign_keys=[approved_by])
    assigned_supervisor = relationship("User", foreign_keys=[assigned_supervisor_id])
    documents = relationship("DocumentProcessing", back_populates="project")
    project_notes = relationship("ProjectNote", back_populates="project", cascade="all, delete-orphan")
    remarks = relationship("ProjectRemark", back_populates="project", cascade="all, delete-orphan")
    result_edits = relationship("ResultEdit", back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_projects_owner_status", "owner_id", "status"),
    )


class DocumentProcessing(Base):
    """Tracks the processing state and results of a single document."""
    __tablename__ = "document_processing"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    file_name = Column(String(512), nullable=False)
    s3_key = Column(String(1024), nullable=False)
    file_size = Column(Integer, nullable=True)
    page_count = Column(Integer, nullable=True)
    status = Column(
        String(50), nullable=False, default="uploading"
    )  # uploading, queued, ocr_processing, llm_processing, validating, completed, failed
    processing_mode = Column(
        String(20), nullable=False, default="auto"
    )  # auto, quick (pdfjs only), deep (aws only)
    processing_path = Column(
        String(20), nullable=True
    )  # pdfjs, aws — which path was actually used
    job_id = Column(String(255), nullable=True, index=True)
    results = Column(JSONB, nullable=True)  # Final extracted Q&A results
    confidence_avg = Column(Float, nullable=True)
    fallback_reason = Column(Text, nullable=True)  # Why AWS fallback was triggered
    processing_time_ms = Column(Integer, nullable=True)
    extracted_text = Column(Text, nullable=True)  # Browser-extracted text stored for combined multi-PDF processing
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    project = relationship("Project", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document")
    feedback = relationship("UserFeedback", back_populates="document")

    __table_args__ = (
        Index("ix_docproc_project_status", "project_id", "status"),
        Index("ix_docproc_job", "job_id"),
    )


class DocumentChunk(Base):
    """Text chunks from a document, used for RAG chatbot."""
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("document_processing.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    page_numbers = Column(ARRAY(Integer), nullable=True)
    embedding = Column(ARRAY(Float), nullable=True)  # Vector embedding for RAG
    token_count = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    document = relationship("DocumentProcessing", back_populates="chunks")

    __table_args__ = (
        Index("ix_chunks_document", "document_id"),
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_doc_index"),
    )


class UserFeedback(Base):
    """Thumbs up/down feedback on individual answers."""
    __tablename__ = "user_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("document_processing.id"), nullable=False)
    question_key = Column(String(100), nullable=False)  # e.g., "building_code"
    answer_value = Column(Text, nullable=True)
    feedback_type = Column(String(20), nullable=False)  # thumbs_up, thumbs_down
    corrected_value = Column(Text, nullable=True)  # User's correction if thumbs_down
    remarks = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="feedback")
    document = relationship("DocumentProcessing", back_populates="feedback")

    __table_args__ = (
        Index("ix_feedback_document", "document_id"),
        UniqueConstraint("user_id", "document_id", "question_key", name="uq_feedback_user_doc_q"),
    )


class Ticket(Base):
    """Support ticket submissions."""
    __tablename__ = "tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    subject = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(50), nullable=True)  # bug, feature, question, other
    priority = Column(String(20), default="medium")  # low, medium, high, urgent
    status = Column(String(20), default="open")  # open, in_progress, resolved, closed
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    resolution = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="tickets")
    assignee = relationship("User", foreign_keys=[assigned_to])


class AnalyticsEvent(Base):
    """Usage tracking and analytics events."""
    __tablename__ = "analytics_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    event_type = Column(String(100), nullable=False)  # upload, process, view_results, etc.
    event_data = Column(JSONB, nullable=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("document_processing.id"), nullable=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    processing_path = Column(String(20), nullable=True)  # pdfjs, aws
    processing_time_ms = Column(Integer, nullable=True)
    confidence_score = Column(Float, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_analytics_event_type", "event_type"),
        Index("ix_analytics_created", "created_at"),
        Index("ix_analytics_user", "user_id"),
    )


class ProjectNote(Base):
    """Notes attached to a project."""
    __tablename__ = "project_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="project_notes")
    user = relationship("User")

    __table_args__ = (
        Index("ix_project_notes_project", "project_id"),
    )


class ProjectRemark(Base):
    """Row-level remarks on project results."""
    __tablename__ = "project_remarks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    project_hash = Column(String(255), nullable=False, index=True)
    row_id = Column(String(255), nullable=False)
    remark_text = Column(Text, nullable=False)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_by_full_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="remarks")
    user = relationship("User")

    __table_args__ = (
        Index("ix_remarks_project_hash", "project_hash"),
        Index("ix_remarks_row", "project_hash", "row_id"),
    )


class ResultEdit(Base):
    """Audit trail for all edits to processing results."""
    __tablename__ = "result_edits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    project_hash = Column(String(255), nullable=False, index=True)
    row_id = Column(String(255), nullable=False)
    column_name = Column(String(255), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    edited_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    edited_by_full_name = Column(String(255), nullable=True)
    question_id = Column(Integer, nullable=True)
    question_text = Column(Text, nullable=True)
    category = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    project = relationship("Project", back_populates="result_edits")
    user = relationship("User")

    __table_args__ = (
        Index("ix_result_edits_project_hash", "project_hash"),
        Index("ix_result_edits_row", "project_hash", "row_id"),
    )


class FeedbackSurvey(Base):
    """User feedback surveys."""
    __tablename__ = "feedback_surveys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    data = Column(JSONB, nullable=True)
    status = Column(String(20), default="draft")  # draft, submitted
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User")

    __table_args__ = (
        Index("ix_feedback_surveys_user", "user_id"),
    )
