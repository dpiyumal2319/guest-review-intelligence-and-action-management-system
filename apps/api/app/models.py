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
