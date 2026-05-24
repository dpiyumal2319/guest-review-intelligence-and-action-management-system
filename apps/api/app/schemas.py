from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    service: str


class ReviewSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    source_type: str
    description: str
    default_enabled: bool
    is_verified_channel: bool
    connector_key: str | None
    sample_import_path: str | None
    source_metadata: dict = Field(serialization_alias="metadata")


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    description: str
    service_level_hours: int
    sort_order: int


class IssueCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    description: str
    is_positive_signal: bool
    sort_order: int


class CategoryDepartmentMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_code: str
    department_code: str
    is_primary: bool
    routing_notes: str


class SeverityThresholdResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_code: str
    low_rating_max: float
    negative_sentiment_max: float
    urgent_confidence_min: float
    recurring_count_7d_min: int
    description: str


class DemoRoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    description: str
    permissions: list[str]
    department_scope: list[str]


class ReferenceConfigResponse(BaseModel):
    review_sources: list[ReviewSourceResponse]
    departments: list[DepartmentResponse]
    issue_categories: list[IssueCategoryResponse]
    category_department_mappings: list[CategoryDepartmentMappingResponse]
    severity_thresholds: list[SeverityThresholdResponse]
    demo_roles: list[DemoRoleResponse]


class IngestionRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    connector_key: str
    source_code: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    records_seen: int
    records_created: int
    records_updated: int
    records_skipped: int
    records_duplicate_flagged: int
    error_count: int
    errors: list[str]


class IngestionSourceStatusResponse(BaseModel):
    source_code: str
    source_name: str
    connector_key: str | None
    source_type: str
    is_verified_channel: bool
    latest_run: IngestionRunResponse | None
    errors: list[str]


class IngestionSourceStatusesResponse(BaseModel):
    sources: list[IngestionSourceStatusResponse]


class ApifyDatasetImportRequest(BaseModel):
    file_path: str | None = Field(
        default=None,
        description="Server-local path to an offline Apify JSON or CSV export.",
    )
    content: str | None = Field(
        default=None,
        description="Raw JSON or CSV export content for offline dataset preparation.",
    )
    file_name: str | None = Field(
        default=None,
        description="Original export file name used to infer JSON or CSV when content is supplied.",
    )
    actor_name: str | None = None
    export_date: str | None = None
    platform: str | None = None
    source_url: str | None = None


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_code: str
    source_name: str
    source_type: str
    is_verified_channel: bool
    external_review_id: str
    reviewer_name: str | None
    review_date: datetime | None
    rating: float | None
    language: str
    title: str | None
    body: str
    content_hash: str
    is_content_duplicate: bool
    duplicate_of_review_id: int | None
    sentiment_label: str
    sentiment_score: float
    issue_category_code: str
    severity: str
    department_code: str
    action_status: str
    updated_at: datetime


class ReviewsResponse(BaseModel):
    reviews: list[ReviewResponse]


class IngestionRunsResponse(BaseModel):
    runs: list[IngestionRunResponse]
