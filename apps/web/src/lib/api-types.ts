export type ReviewAnalysis = {
  id: number
  sentiment_label: string
  sentiment_score: number
  sentiment_confidence: number
  department_code: string
  department_confidence: number
  department_model_name: string
  reputation_risk_score: number
  reputation_risk_label: string
  embedding: number[] | null
  embedding_model_name: string | null
  embedding_generated_at: string | null
  analysis_version: string
  explanation_factors: Record<string, unknown>
  analyzed_at: string
  is_active: boolean
}

export type IssueReviewLink = {
  id: number
  issue_id: number
  review_id: number
  similarity_score: number
  linked_at: string
  is_triggering_evidence: boolean
  evidence_snippet: string | null
  review_source_code: string | null
  review_source_name: string | null
  review_external_id: string | null
  review_reviewer_name: string | null
  review_date: string | null
  review_rating: number | null
  review_body: string | null
  review_url: string | null
}

export type Review = {
  id: number
  source_code: string
  source_name: string
  is_verified_channel: boolean
  external_review_id: string
  reviewer_name: string | null
  display_external_review_id: string
  display_reviewer_name: string | null
  review_date: string | null
  rating: number | null
  language: string
  title: string | null
  display_title: string | null
  body: string
  display_body: string
  has_display_redactions: boolean
  redacted_display_fields: string[]
  content_hash: string
  is_content_duplicate: boolean
  duplicate_of_review_id: number | null
  updated_at: string
  analysis: ReviewAnalysis | null
  issue_links: IssueReviewLink[]
}

export type ReviewsResponse = {
  reviews: Review[]
  total: number
  page: number
  per_page: number
  total_pages: number
}

export type Department = {
  code: string
  name: string
  description: string
  service_level_hours: number
  risk_weight: number
}

export type ReviewSource = {
  code: string
  name: string
  is_verified_channel: boolean
}

export type DemoRole = {
  code: string
  name: string
  description: string
  permissions: string[]
  department_scope: string[]
}

export type ReferenceConfig = {
  review_sources: ReviewSource[]
  departments: Department[]
  demo_roles: DemoRole[]
}

export type IngestionRun = {
  id: number
  connector_key: string
  source_code: string
  status: string
  started_at: string
  completed_at: string | null
  records_seen: number
  records_created: number
  records_updated: number
  records_skipped: number
  records_duplicate_flagged: number
  error_count: number
  errors: string[]
}

export type IssueEvent = {
  id: number
  issue_id: number
  event_type: string
  actor: string
  old_value: string | null
  new_value: string | null
  note: string | null
  created_at: string
}

export type DetectedIssueCompact = {
  id: number
  title: string
  description: string | null
  department_code: string
  status: string
  priority: string
  reputation_risk_score: number
  recurrence_count: number
  first_seen_at: string
  last_seen_at: string
  resolved_at: string | null
  recurred_at: string | null
  assignee_name: string | null
  keywords: string[]
  title_quality_score: number | null
  merged_from_id: number | null
  created_at: string
  updated_at: string
}

export type DetectedIssue = DetectedIssueCompact & {
  cluster_key: string
  cluster_centroid: number[]
  embedding_model_name: string
  title_generated_by: string
  title_generation_model: string | null
  title_confidence: number | null
  review_links: IssueReviewLink[]
  events: IssueEvent[]
}

export type IssuesResponse = {
  issues: DetectedIssueCompact[]
  total: number
  page: number
  per_page: number
  total_pages: number
}

export type IssueEmerging = {
  id: number
  title: string
  department_code: string
  priority: string
  reputation_risk_score: number
  recurrence_count: number
  representative_snippet: string
  review_id: number | null
  source_code: string | null
  keywords: string[]
  first_seen_at: string
  last_seen_at: string
}

export type IssueEmergingList = {
  items: IssueEmerging[]
  total_high_risk: number
  total_emerging: number
}

export type IssueDetectResponse = {
  created: number
  updated: number
  linked: number
  merged: number
  issues: DetectedIssueCompact[]
}

export type OverviewCount = {
  code: string
  count: number
}

export type OverviewKpi = {
  total_reviews: number
  average_rating: number | null
  average_reputation_risk_score: number
  sentiment_mix: Record<string, number>
  reputation_risk_mix: Record<string, number>
  top_departments: OverviewCount[]
  active_issues: number
  recurred_issues: number
  high_risk_issues: number
  priority_distribution: Record<string, number>
  department_issue_counts: Record<string, number>
  filters_applied: Record<string, string | null>
}

export type DashboardDrillThrough = {
  path: string
  filters: Record<string, string>
}

export type DashboardActionMetric = {
  review_count: number
  drill_through: DashboardDrillThrough
}

export type DashboardIssueMetric = {
  issue_count: number
  drill_through: DashboardDrillThrough
}

export type DashboardAgingRisk = {
  review_count: number
  threshold_days: number
  oldest_review_date: string | null
  drill_through: DashboardDrillThrough
}

export type DashboardOwnerPressureItem = {
  department_code: string
  active_issues: number
  high_risk_issues: number
  issues_drill_through: DashboardDrillThrough
  reviews_drill_through: DashboardDrillThrough
}

export type DashboardPlatformRiskItem = {
  source_code: string
  high_risk_reviews: number
  drill_through: DashboardDrillThrough
}

export type DashboardIssueItem = {
  issue_id: number
  title: string
  department_code: string
  status: string
  priority: string
  reputation_risk_score: number
  recurrence_count: number
  first_seen_at: string
  last_seen_at: string
  issues_drill_through: DashboardDrillThrough
  reviews_drill_through: DashboardDrillThrough
}

export type OverviewActionAnalytics = {
  active_issues: DashboardIssueMetric
  high_risk_issues: DashboardIssueMetric
  recurred_issues: DashboardIssueMetric
  action_leakage: DashboardActionMetric
  aging_risk: DashboardAgingRisk
  owner_pressure: DashboardOwnerPressureItem[]
  platform_risk_spread: DashboardPlatformRiskItem[]
  recent_issues: DashboardIssueItem[]
  filters_applied: Record<string, string | null>
}

export type SemanticDuplicatePair = {
  review_id: number
  matched_review_id: number
  similarity: number
  department_code: string
}

export type SemanticIssueCluster = {
  cluster_id: string
  size: number
  representative_review_id: number
  representative_text: string
  department_code: string
  source_mix: Record<string, number>
  review_ids: number[]
  average_similarity: number
}

export type SemanticAnalysis = {
  embedding_strategy: string
  embedding_model_name: string
  embedding_model_version: string
  embedding_fallback_note: string
  similarity_threshold: number
  min_cluster_size: number
  near_duplicate_pairs: SemanticDuplicatePair[]
  clusters: SemanticIssueCluster[]
}

export const SENTIMENT_LABELS = ["positive", "mixed", "negative"] as const
export const REPUTATION_RISK_LABELS = ["low", "medium", "high", "critical"] as const
export const ISSUE_STATUSES = ["active", "resolved", "recurred"] as const
export const ISSUE_PRIORITIES = ["low", "medium", "high", "urgent"] as const
