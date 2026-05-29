from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ReviewSource(Base):
    __tablename__ = "review_sources"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
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
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class IssueCategory(Base):
    __tablename__ = "issue_categories"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_positive_signal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    department_mappings: Mapped[list["CategoryDepartmentMapping"]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
    )
    severity_threshold: Mapped["SeverityThreshold"] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
    )


class CategoryDepartmentMapping(Base):
    __tablename__ = "category_department_mappings"

    category_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("issue_categories.code", ondelete="CASCADE"),
        primary_key=True,
    )
    department_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("departments.code", ondelete="RESTRICT"),
        primary_key=True,
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    routing_notes: Mapped[str] = mapped_column(Text, nullable=False)

    category: Mapped[IssueCategory] = relationship(back_populates="department_mappings")
    department: Mapped[Department] = relationship()


class SeverityThreshold(Base):
    __tablename__ = "severity_thresholds"

    category_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("issue_categories.code", ondelete="CASCADE"),
        primary_key=True,
    )
    low_rating_max: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    negative_sentiment_max: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    urgent_confidence_min: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    recurring_count_7d_min: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    category: Mapped[IssueCategory] = relationship(back_populates="severity_threshold")


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
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2))
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    title: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_content_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duplicate_of_review_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("normalized_reviews.id", ondelete="SET NULL"),
    )
    sentiment_label: Mapped[str] = mapped_column(String(32), nullable=False)
    sentiment_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    issue_category_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("issue_categories.code", ondelete="RESTRICT"),
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    department_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("departments.code", ondelete="RESTRICT"),
        nullable=False,
    )
    action_status: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    normalized_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    raw_review: Mapped[RawReview] = relationship()
    source: Mapped[ReviewSource] = relationship()
    issue_category: Mapped[IssueCategory] = relationship()
    department: Mapped[Department] = relationship()
    analysis: Mapped["ReviewAnalysis | None"] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
        uselist=False,
    )

    @property
    def source_name(self) -> str:
        return self.source.name

    @property
    def source_type(self) -> str:
        return self.source.source_type

    @property
    def is_verified_channel(self) -> bool:
        return self.source.is_verified_channel


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
    sentiment_score: Mapped[float] = mapped_column(Numeric(5, 3), nullable=False)
    sentiment_confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    issue_category_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("issue_categories.code", ondelete="RESTRICT"),
        nullable=False,
    )
    severity_score: Mapped[int] = mapped_column(Integer, nullable=False)
    severity_label: Mapped[str] = mapped_column(String(32), nullable=False)
    department_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("departments.code", ondelete="RESTRICT"),
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    analysis_version: Mapped[str] = mapped_column(String(64), nullable=False)
    explanation_factors: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    review: Mapped[NormalizedReview] = relationship(back_populates="analysis")
    issue_category: Mapped[IssueCategory] = relationship()
    department: Mapped[Department] = relationship()
    issue_category_predictions: Mapped[list["ReviewIssueCategoryPrediction"]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        order_by="ReviewIssueCategoryPrediction.rank",
    )


class ActionTicket(Base):
    __tablename__ = "action_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("normalized_reviews.id", ondelete="RESTRICT"),
        nullable=True,
    )
    department_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("departments.code", ondelete="RESTRICT"),
        nullable=False,
    )
    source_group_type: Mapped[str | None] = mapped_column(String(64))
    source_group_key: Mapped[str | None] = mapped_column(String(120))
    source_group_label: Mapped[str | None] = mapped_column(String(255))
    source_category_code: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("issue_categories.code", ondelete="RESTRICT"),
    )
    source_cluster_id: Mapped[str | None] = mapped_column(String(120))
    source_review_ids: Mapped[list[int] | None] = mapped_column(JSON)
    priority: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    assignee_name: Mapped[str | None] = mapped_column(String(120))
    assignee_email: Mapped[str | None] = mapped_column(String(255))
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    review: Mapped["NormalizedReview | None"] = relationship()
    department: Mapped[Department] = relationship()
    source_category: Mapped[IssueCategory | None] = relationship()
    events: Mapped[list["TicketEvent"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketEvent.occurred_at",
    )


class TicketEvent(Base):
    __tablename__ = "ticket_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("action_tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[str | None] = mapped_column(String(255))
    new_value: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    ticket: Mapped[ActionTicket] = relationship(back_populates="events")


class ReviewIssueCategoryPrediction(Base):
    __tablename__ = "review_issue_category_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("review_analyses.id", ondelete="CASCADE"),
        nullable=False,
    )
    category_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("issue_categories.code", ondelete="RESTRICT"),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    department_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("departments.code", ondelete="RESTRICT"),
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    analysis: Mapped[ReviewAnalysis] = relationship(back_populates="issue_category_predictions")
    category: Mapped[IssueCategory] = relationship()
    department: Mapped[Department] = relationship()
