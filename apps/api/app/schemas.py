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


class ReviewAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sentiment_label: str
    sentiment_score: float
    sentiment_confidence: float
    issue_category_code: str
    severity_score: int
    severity_label: str
    department_code: str
    model_name: str
    model_version: str
    analysis_version: str
    explanation_factors: dict
    analyzed_at: datetime
    is_active: bool
    issue_category_predictions: list["IssueCategoryPredictionResponse"] = []


class IssueCategoryPredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_code: str
    confidence: float
    rank: int
    is_primary: bool
    department_code: str
    model_name: str
    model_version: str
    analyzed_at: datetime


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
    analysis: ReviewAnalysisResponse | None


class ReviewsResponse(BaseModel):
    reviews: list[ReviewResponse]


class SemanticDuplicatePairResponse(BaseModel):
    review_id: int
    matched_review_id: int
    similarity: float
    category_code: str
    department_code: str


class SemanticIssueClusterResponse(BaseModel):
    cluster_id: str
    size: int
    representative_review_id: int
    representative_text: str
    category_code: str
    department_code: str
    source_mix: dict[str, int]
    review_ids: list[int]
    average_similarity: float


class SemanticAnalysisResponse(BaseModel):
    embedding_model_name: str
    embedding_model_version: str
    embedding_fallback_note: str
    similarity_threshold: float
    min_cluster_size: int
    near_duplicate_pairs: list[SemanticDuplicatePairResponse]
    clusters: list[SemanticIssueClusterResponse]


class IngestionRunsResponse(BaseModel):
    runs: list[IngestionRunResponse]


class ReanalysisResponse(BaseModel):
    analyzed_count: int


class OverviewCategoryCountResponse(BaseModel):
    code: str
    count: int


class OverviewDepartmentCountResponse(BaseModel):
    code: str
    count: int


class OverviewKpiResponse(BaseModel):
    total_reviews: int
    average_rating: float | None
    average_severity_score: int
    sentiment_mix: dict[str, int]
    severity_mix: dict[str, int]
    action_status_mix: dict[str, int]
    top_departments: list[OverviewDepartmentCountResponse]
    top_categories: list[OverviewCategoryCountResponse]
    include_social_listening: bool
    filters_applied: dict[str, str | None]


class TicketCreateRequest(BaseModel):
    department_code: str
    priority: str = Field(description="low, medium, high, or urgent")
    assignee_name: str | None = None
    assignee_email: str | None = None
    due_date: datetime | None = None
    notes: str | None = None


class TicketUpdateRequest(BaseModel):
    status: str | None = Field(default=None, description="open, in_progress, blocked, resolved, or verified")
    priority: str | None = None
    assignee_name: str | None = None
    assignee_email: str | None = None
    due_date: datetime | None = None
    notes: str | None = None


class TicketEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    event_type: str
    old_value: str | None
    new_value: str | None
    note: str | None
    occurred_at: datetime


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    review_id: int
    department_code: str
    priority: str
    status: str
    assignee_name: str | None
    assignee_email: str | None
    due_date: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    events: list[TicketEventResponse] = []


class TicketsResponse(BaseModel):
    tickets: list[TicketResponse]
