export type IssueCategoryPrediction = {
  id: number
  category_code: string
  confidence: number
  rank: number
  is_primary: boolean
  department_code: string
  model_name: string
  model_version: string
  analyzed_at: string
}

export type ReviewAnalysis = {
  id: number
  sentiment_label: string
  sentiment_score: number
  sentiment_confidence: number
  issue_category_code: string
  severity_score: number
  severity_label: string
  department_code: string
  model_name: string
  model_version: string
  analysis_version: string
  analyzed_at: string
  is_active: boolean
  issue_category_predictions: IssueCategoryPrediction[]
  explanation_factors: {
    model?: { fallback_note?: string }
    signals?: {
      recurrence_count_7d?: number
      duplicate_signal?: boolean
      urgency_terms?: string[]
    }
  }
}

export type Review = {
  id: number
  source_code: string
  source_name: string
  source_type: string
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
  sentiment_label: string
  sentiment_score: number
  issue_category_code: string
  severity: string
  department_code: string
  action_status: string
  updated_at: string
  analysis: ReviewAnalysis | null
}

export type IssueCategory = {
  code: string
  name: string
  description: string
  is_positive_signal: boolean
  sort_order: number
}

export type Department = {
  code: string
  name: string
  description: string
  service_level_hours: number
  sort_order: number
}

export type ReviewSource = {
  code: string
  name: string
  source_type: string
  is_verified_channel: boolean
}

export type ReferenceConfig = {
  review_sources: ReviewSource[]
  departments: Department[]
  issue_categories: IssueCategory[]
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

export type IngestionSourceStatus = {
  source_code: string
  source_name: string
  connector_key: string | null
  source_type: string
  is_verified_channel: boolean
  latest_run: IngestionRun | null
  errors: string[]
}

export type TicketEvent = {
  id: number
  ticket_id: number
  event_type: string
  old_value: string | null
  new_value: string | null
  note: string | null
  occurred_at: string
}

export type Ticket = {
  id: number
  review_id: number | null
  department_code: string
  source_group_type: string | null
  source_group_key: string | null
  source_group_label: string | null
  source_category_code: string | null
  source_cluster_id: string | null
  source_review_ids: number[] | null
  priority: string
  status: string
  assignee_name: string | null
  assignee_email: string | null
  due_date: string | null
  notes: string | null
  created_at: string
  updated_at: string
  events: TicketEvent[]
}

export type IssueSummaryItem = {
  category_code: string
  category_name: string
  review_count: number
  average_severity_score: number
  primary_department_code: string
  source_mix: Record<string, number>
  representative_review_id: number
  linked_ticket_ids: number[]
}

export type IssueSummary = {
  items: IssueSummaryItem[]
  total_reviews: number
  include_social_listening: boolean
  filters_applied: Record<string, string | null>
}

export type SemanticDuplicatePair = {
  review_id: number
  matched_review_id: number
  similarity: number
  category_code: string
  department_code: string
}

export type SemanticIssueCluster = {
  cluster_id: string
  size: number
  representative_review_id: number
  representative_text: string
  category_code: string
  department_code: string
  source_mix: Record<string, number>
  review_ids: number[]
  average_similarity: number
  linked_ticket_ids: number[]
}

export type SemanticAnalysis = {
  embedding_model_name: string
  embedding_model_version: string
  embedding_fallback_note: string
  similarity_threshold: number
  min_cluster_size: number
  near_duplicate_pairs: SemanticDuplicatePair[]
  clusters: SemanticIssueCluster[]
}

export const SENTIMENT_LABELS = ["positive", "mixed", "negative"] as const
export const SEVERITY_LABELS = ["low", "medium", "high", "critical"] as const
export const ACTION_STATUSES = ["new", "reviewed", "ticket_created", "ignored"] as const
export const TICKET_STATUSES = ["open", "in_progress", "blocked", "resolved", "verified"] as const
export const TICKET_PRIORITIES = ["low", "medium", "high", "urgent"] as const
