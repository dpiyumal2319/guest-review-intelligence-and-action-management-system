from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    service: str


class ReviewSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
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
    risk_weight: int


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


class ConnectorImportRequest(BaseModel):
    fixture_path: str | None = None


class IngestionSourceStatusResponse(BaseModel):
    source_code: str
    source_name: str
    connector_key: str | None
    is_verified_channel: bool
    latest_run: IngestionRunResponse | None
    errors: list[str]


class IngestionSourceStatusesResponse(BaseModel):
    sources: list[IngestionSourceStatusResponse]


class ReviewAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sentiment_label: str
    sentiment_score: float
    sentiment_confidence: float
    department_code: str
    department_confidence: float
    department_model_name: str
    reputation_risk_score: int
    reputation_risk_label: str
    embedding: list[float] | None = None
    embedding_model_name: str | None = None
    embedding_generated_at: datetime | None = None
    analysis_version: str
    explanation_factors: dict | None = None
    analyzed_at: datetime
    is_active: bool


class IssueReviewLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    issue_id: int
    review_id: int
    similarity_score: float
    linked_at: datetime
    is_triggering_evidence: bool
    evidence_snippet: str | None = None


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_code: str
    source_name: str
    is_verified_channel: bool
    external_review_id: str
    reviewer_name: str | None
    display_external_review_id: str
    display_reviewer_name: str | None
    review_date: datetime | None
    rating: float | None
    language: str
    title: str | None
    display_title: str | None
    body: str
    display_body: str
    has_display_redactions: bool
    redacted_display_fields: list[str]
    content_hash: str
    is_content_duplicate: bool
    duplicate_of_review_id: int | None
    updated_at: datetime
    analysis: ReviewAnalysisResponse | None
    issue_links: list[IssueReviewLinkResponse] = []


class ReviewsResponse(BaseModel):
    reviews: list[ReviewResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class IngestionRunsResponse(BaseModel):
    runs: list[IngestionRunResponse]


class ReanalysisResponse(BaseModel):
    analyzed_count: int


class SemanticDuplicatePairResponse(BaseModel):
    review_id: int
    matched_review_id: int
    similarity: float
    department_code: str


class SemanticIssueClusterResponse(BaseModel):
    cluster_id: str
    size: int
    representative_review_id: int
    representative_text: str
    department_code: str
    source_mix: dict[str, int]
    review_ids: list[int]
    average_similarity: float


class SemanticAnalysisResponse(BaseModel):
    embedding_strategy: str
    embedding_model_name: str
    embedding_model_version: str
    embedding_fallback_note: str
    similarity_threshold: float
    min_cluster_size: int
    near_duplicate_pairs: list[SemanticDuplicatePairResponse]
    clusters: list[SemanticIssueClusterResponse]


class IssueEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    issue_id: int
    event_type: str
    actor: str
    old_value: str | None
    new_value: str | None
    note: str | None
    created_at: datetime


class DetectedIssueCompactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    department_code: str
    status: str
    priority: str
    reputation_risk_score: int
    recurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None
    recurred_at: datetime | None
    assignee_name: str | None
    created_at: datetime
    updated_at: datetime


class DetectedIssueDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    department_code: str
    status: str
    priority: str
    reputation_risk_score: int
    recurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None
    recurred_at: datetime | None
    assignee_name: str | None
    cluster_key: str
    cluster_centroid: list[float]
    embedding_model_name: str
    title_generated_by: str
    title_generation_model: str | None
    title_confidence: float | None
    created_at: datetime
    updated_at: datetime
    review_links: list[IssueReviewLinkResponse] = []
    events: list[IssueEventResponse] = []


class IssuesResponse(BaseModel):
    issues: list[DetectedIssueCompactResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class IssueEmergingResponse(BaseModel):
    department_code: str
    review_count: int
    avg_similarity: float | None
    risk_scores: list[int]
    representative_snippet: str
    review_ids: list[int]
    first_seen_at: datetime
    last_seen_at: datetime


class IssueDetectResponse(BaseModel):
    created: int
    updated: int
    linked: int
    issues: list[DetectedIssueCompactResponse]


class IssueUpdateRequest(BaseModel):
    assignee_name: str | None = None
    priority: str | None = None


class IssueResolveResponse(BaseModel):
    id: int
    status: str
    resolved_at: datetime


class OverviewDepartmentCountResponse(BaseModel):
    code: str
    count: int


class OverviewKpiResponse(BaseModel):
    total_reviews: int
    average_rating: float | None
    average_reputation_risk_score: int
    sentiment_mix: dict[str, int]
    reputation_risk_mix: dict[str, int]
    top_departments: list[OverviewDepartmentCountResponse]
    active_issues: int
    recurred_issues: int
    high_risk_issues: int
    priority_distribution: dict[str, int]
    department_issue_counts: dict[str, int]
    filters_applied: dict[str, str | None]


class DashboardDrillThroughResponse(BaseModel):
    path: str
    filters: dict[str, str | None]


class DashboardActionMetricResponse(BaseModel):
    review_count: int
    drill_through: DashboardDrillThroughResponse


class DashboardIssueMetricResponse(BaseModel):
    issue_count: int
    drill_through: DashboardDrillThroughResponse


class DashboardAgingRiskResponse(BaseModel):
    review_count: int
    threshold_days: int
    oldest_review_date: datetime | None
    drill_through: DashboardDrillThroughResponse


class DashboardOwnerPressureItemResponse(BaseModel):
    department_code: str
    active_issues: int
    high_risk_issues: int
    issues_drill_through: DashboardDrillThroughResponse
    reviews_drill_through: DashboardDrillThroughResponse


class DashboardPlatformRiskItemResponse(BaseModel):
    source_code: str
    high_risk_reviews: int
    drill_through: DashboardDrillThroughResponse


class DashboardIssueItemResponse(BaseModel):
    issue_id: int
    title: str
    department_code: str
    status: str
    priority: str
    reputation_risk_score: int
    recurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    issues_drill_through: DashboardDrillThroughResponse
    reviews_drill_through: DashboardDrillThroughResponse


class OverviewActionAnalyticsResponse(BaseModel):
    active_issues: DashboardIssueMetricResponse
    high_risk_issues: DashboardIssueMetricResponse
    recurred_issues: DashboardIssueMetricResponse
    action_leakage: DashboardActionMetricResponse
    aging_risk: DashboardAgingRiskResponse
    owner_pressure: list[DashboardOwnerPressureItemResponse]
    platform_risk_spread: list[DashboardPlatformRiskItemResponse]
    recent_issues: list[DashboardIssueItemResponse]
    filters_applied: dict[str, str | None]
