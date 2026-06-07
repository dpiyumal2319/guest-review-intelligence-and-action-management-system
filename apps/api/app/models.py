from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.redaction import redact_display_text, redacted_fields_for_values


class Base(DeclarativeBase):
    pass


class ReviewSource(Base):
    __tablename__ = "review_sources"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    default_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_verified_channel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    connector_key: Mapped[str | None] = mapped_column(String(120))
    sample_import_path: Mapped[str | None] = mapped_column(String(255))
    source_metadata: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)


class Department(Base):
    __tablename__ = "departments"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    service_level_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_weight: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class DemoRole(Base):
    __tablename__ = "demo_roles"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    department_scope: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_key: Mapped[str] = mapped_column(String(120), nullable=False)
    source_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("review_sources.code", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_duplicate_flagged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    source: Mapped[ReviewSource] = relationship()


class RawReview(Base):
    __tablename__ = "raw_reviews"
    __table_args__ = (
        UniqueConstraint("source_code", "external_review_id", name="uq_raw_reviews_source_external_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("review_sources.code", ondelete="RESTRICT"),
        nullable=False,
    )
    external_review_id: Mapped[str] = mapped_column(String(120), nullable=False)
    ingestion_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ingestion_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    ingestion_run: Mapped[IngestionRun] = relationship()
    source: Mapped[ReviewSource] = relationship()


class NormalizedReview(Base):
    __tablename__ = "normalized_reviews"
    __table_args__ = (
        UniqueConstraint("source_code", "external_review_id", name="uq_normalized_reviews_source_external_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_review_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("raw_reviews.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    source_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("review_sources.code", ondelete="RESTRICT"),
        nullable=False,
    )
    external_review_id: Mapped[str] = mapped_column(String(120), nullable=False)
    reviewer_name: Mapped[str | None] = mapped_column(String(120))
    review_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rating: Mapped[float | None] = mapped_column(Float)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    title: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_content_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duplicate_of_review_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("normalized_reviews.id", ondelete="SET NULL"),
    )
    normalized_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    raw_review: Mapped[RawReview] = relationship()
    source: Mapped[ReviewSource] = relationship()
    analysis: Mapped["ReviewAnalysis | None"] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
        uselist=False,
    )
    issue_links: Mapped[list["IssueReviewLink"]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
    )

    @property
    def source_name(self) -> str:
        return self.source.name

    @property
    def is_verified_channel(self) -> bool:
        return self.source.is_verified_channel

    @property
    def display_reviewer_name(self) -> str | None:
        return redact_display_text(self.reviewer_name).value

    @property
    def display_external_review_id(self) -> str:
        return redact_display_text(self.external_review_id).value or ""

    @property
    def display_title(self) -> str | None:
        return redact_display_text(self.title).value

    @property
    def display_body(self) -> str:
        return redact_display_text(self.body).value or ""

    @property
    def has_display_redactions(self) -> bool:
        return bool(self.redacted_display_fields)

    @property
    def redacted_display_fields(self) -> list[str]:
        return redacted_fields_for_values(
            {
                "reviewer_name": self.reviewer_name,
                "external_review_id": self.external_review_id,
                "title": self.title,
                "body": self.body,
            }
        )


class ReviewAnalysis(Base):
    __tablename__ = "review_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("normalized_reviews.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    sentiment_label: Mapped[str] = mapped_column(String(32), nullable=False)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False)
    sentiment_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    department_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("departments.code", ondelete="RESTRICT"),
        nullable=False,
    )
    department_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    department_model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    reputation_risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    reputation_risk_label: Mapped[str] = mapped_column(String(32), nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(JSON)
    embedding_model_name: Mapped[str | None] = mapped_column(String(120))
    embedding_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    analysis_version: Mapped[str] = mapped_column(String(64), nullable=False)
    explanation_factors: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    review: Mapped[NormalizedReview] = relationship(back_populates="analysis")
    department: Mapped[Department] = relationship()


class DetectedIssue(Base):
    __tablename__ = "detected_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    department_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("departments.code", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    reputation_risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    recurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assignee_name: Mapped[str | None] = mapped_column(String(120))
    cluster_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    cluster_centroid: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    embedding_model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    title_generated_by: Mapped[str] = mapped_column(String(32), nullable=False)
    title_generation_model: Mapped[str | None] = mapped_column(String(120))
    title_confidence: Mapped[float | None] = mapped_column(Float)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    title_quality_score: Mapped[float | None] = mapped_column(Float)
    merged_from_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    department: Mapped[Department] = relationship()
    review_links: Mapped[list["IssueReviewLink"]] = relationship(
        back_populates="issue",
        cascade="all, delete-orphan",
    )
    events: Mapped[list["IssueEvent"]] = relationship(
        back_populates="issue",
        cascade="all, delete-orphan",
        order_by="IssueEvent.created_at",
    )


class IssueReviewLink(Base):
    __tablename__ = "issue_review_links"
    __table_args__ = (
        UniqueConstraint("issue_id", "review_id", name="uq_issue_review_link"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("detected_issues.id", ondelete="CASCADE"),
        nullable=False,
    )
    review_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("normalized_reviews.id", ondelete="CASCADE"),
        nullable=False,
    )
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_triggering_evidence: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence_snippet: Mapped[str | None] = mapped_column(Text)

    issue: Mapped[DetectedIssue] = relationship(back_populates="review_links")
    review: Mapped[NormalizedReview] = relationship(back_populates="issue_links")


class IssueEvent(Base):
    __tablename__ = "issue_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("detected_issues.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    old_value: Mapped[str | None] = mapped_column(String(255))
    new_value: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    issue: Mapped[DetectedIssue] = relationship(back_populates="events")
