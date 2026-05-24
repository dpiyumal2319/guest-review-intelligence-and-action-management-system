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
