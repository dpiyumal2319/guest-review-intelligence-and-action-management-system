from sqlalchemy import Boolean, ForeignKey, Integer, JSON, Numeric, String, Text
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
