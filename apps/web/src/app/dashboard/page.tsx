"use client"

import type * as React from "react"
import { useCallback, useEffect, useMemo, useState } from "react"
import {
  Bar,
  BarChart,
  CartesianGrid,
  XAxis,
} from "recharts"

import { AppSidebar } from "@/components/app-sidebar"
import { SiteHeader } from "@/components/site-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"
import { useDemoRole } from "@/hooks/use-demo-role"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"

const sentimentConfig = {
  reviews: {
    label: "Reviews",
    color: "var(--chart-1)",
  },
} satisfies ChartConfig

const issueConfig = {
  count: {
    label: "Reviews",
    color: "var(--chart-2)",
  },
} satisfies ChartConfig

const queues = [
  {
    title: "Reviews",
    id: "reviews",
    body: "Searchable normalized review queue with source, rating, sentiment, category, severity, and action status filters.",
    status: "Shell ready",
  },
  {
    title: "Issues",
    id: "issues",
    body: "Recurring issue categories and semantic clusters will surface operational patterns before ticket creation.",
    status: "Awaiting pipeline",
  },
  {
    title: "Tickets",
    id: "tickets",
    body: "Department-owned corrective actions will track priority, status, notes, resolution, and verification.",
    status: "Workflow next",
  },
  {
    title: "Ingestion",
    id: "ingestion",
    body: "Manual connector runs for Google Business Profile, Booking.com, and Tripadvisor review platforms.",
    status: "API hook next",
  },
]

type Review = {
  id: number
  source_code: string
  source_name: string
  is_verified_channel: boolean
  external_review_id: string
  reviewer_name: string | null
  review_date: string | null
  rating: number | null
  title: string | null
  body: string
  content_hash: string
  is_content_duplicate: boolean
  duplicate_of_review_id: number | null
  sentiment_label: string
  sentiment_score: number
  issue_category_code: string
  severity: string
  department_code: string
  action_status: string
  analysis: ReviewAnalysis | null
}

type ReviewAnalysis = {
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
    model?: {
      fallback_note?: string
    }
    signals?: {
      recurrence_count_7d?: number
      duplicate_signal?: boolean
      urgency_terms?: string[]
    }
  }
}

type IssueCategoryPrediction = {
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

type IssueCategory = {
  code: string
  name: string
  is_positive_signal: boolean
}

type Department = {
  code: string
  name: string
}

type IngestionRun = {
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

type IngestionSourceStatus = {
  source_code: string
  source_name: string
  connector_key: string | null
  is_verified_channel: boolean
  latest_run: IngestionRun | null
  errors: string[]
}

type SemanticDuplicatePair = {
  review_id: number
  matched_review_id: number
  similarity: number
  category_code: string
  department_code: string
}

type SemanticIssueCluster = {
  cluster_id: string
  size: number
  representative_review_id: number
  representative_text: string
  category_code: string
  department_code: string
  source_mix: Record<string, number>
  review_ids: number[]
  average_similarity: number
}

type SemanticAnalysis = {
  embedding_strategy: string
  embedding_model_name: string
  embedding_model_version: string
  embedding_fallback_note: string
  similarity_threshold: number
  min_cluster_size: number
  near_duplicate_pairs: SemanticDuplicatePair[]
  clusters: SemanticIssueCluster[]
}

type OverviewCount = {
  code: string
  count: number
}

type OverviewKpi = {
  total_reviews: number
  average_rating: number | null
  average_severity_score: number
  sentiment_mix: Record<string, number>
  severity_mix: Record<string, number>
  action_status_mix: Record<string, number>
  top_departments: OverviewCount[]
  top_categories: OverviewCount[]
  filters_applied: Record<string, string | null>
}

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

function formatDate(value: string | null) {
  if (!value) {
    return "Not recorded"
  }
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value))
}

export default function Page() {
  const { activeRole, departments: scopedDepartments, effectiveDepartmentCode, scopeLabel, workflowLabel } = useDemoRole()
  const [reviews, setReviews] = useState<Review[]>([])
  const [runs, setRuns] = useState<IngestionRun[]>([])
  const [sourceStatuses, setSourceStatuses] = useState<IngestionSourceStatus[]>([])
  const [issueCategories, setIssueCategories] = useState<IssueCategory[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [semanticAnalysis, setSemanticAnalysis] = useState<SemanticAnalysis | null>(null)
  const [overviewKpi, setOverviewKpi] = useState<OverviewKpi | null>(null)
  const [issueCategoryFilter, setIssueCategoryFilter] = useState("all")
  const [departmentFilter, setDepartmentFilter] = useState("all")
  const [isLoading, setIsLoading] = useState(true)
  const [importingConnector, setImportingConnector] = useState<string | null>(null)
  const [isReanalyzing, setIsReanalyzing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const latestRun = runs[0]
  const verifiedSourceStatuses = useMemo(
    () => sourceStatuses.filter((source) => source.is_verified_channel && source.connector_key),
    [sourceStatuses]
  )
  const issueCategoryNameByCode = useMemo(
    () => Object.fromEntries(issueCategories.map((category) => [category.code, category.name])),
    [issueCategories]
  )
  const departmentNameByCode = useMemo(
    () => Object.fromEntries(departments.map((department) => [department.code, department.name])),
    [departments]
  )
  const activeAnalyses = useMemo(
    () => reviews.map((review) => review.analysis).filter((analysis): analysis is ReviewAnalysis => analysis !== null),
    [reviews]
  )
  const importedMetrics = useMemo(() => {
    const kpiSentimentNegative = overviewKpi?.sentiment_mix?.negative ?? 0
    const kpiTotal = overviewKpi?.total_reviews ?? 0
    const kpiSeverityHigh = (overviewKpi?.severity_mix?.high ?? 0) + (overviewKpi?.severity_mix?.critical ?? 0)
    const kpiTopDepartment = overviewKpi?.top_departments?.[0]
    return [
      {
        label: "Imported records",
        value: kpiTotal.toString(),
        detail: latestRun ? `Review platforms · last run ${latestRun.status}` : "Review platforms",
      },
      {
        label: "Negative sentiment",
        value: kpiTotal ? `${Math.round((kpiSentimentNegative / kpiTotal) * 100)}%` : "0%",
        detail: `${kpiSentimentNegative} of ${kpiTotal} records`,
      },
      {
        label: "High severity",
        value: kpiSeverityHigh.toString(),
        detail: `average severity score ${overviewKpi?.average_severity_score ?? 0}`,
      },
      {
        label: "Department focus",
        value: kpiTopDepartment ? (departmentNameByCode[kpiTopDepartment.code] ?? kpiTopDepartment.code.replaceAll("_", " ")) : "N/A",
        detail: kpiTopDepartment ? `${kpiTopDepartment.count} assigned reviews` : "no analysis results yet",
      },
      {
        label: "Average rating",
        value: overviewKpi?.average_rating != null ? overviewKpi.average_rating.toFixed(2) : "N/A",
        detail: overviewKpi ? "Google Business Profile, Booking.com, and Tripadvisor" : "run a connector import to compute KPIs",
      },
    ]
  }, [departmentNameByCode, latestRun, overviewKpi])
  const sentimentData = useMemo(
    () =>
      ["positive", "mixed", "negative"].map((sentiment) => ({
        sentiment,
        reviews: activeAnalyses.filter((analysis) => analysis.sentiment_label === sentiment).length,
      })),
    [activeAnalyses]
  )
  const issueData = useMemo(() => {
    const counts = activeAnalyses.reduce<Record<string, number>>((totals, analysis) => {
      for (const prediction of analysis.issue_category_predictions.filter((prediction) => prediction.is_primary)) {
        totals[prediction.category_code] = (totals[prediction.category_code] ?? 0) + 1
      }
      return totals
    }, {})
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([category, count]) => ({ category: issueCategoryNameByCode[category] ?? category.replaceAll("_", " "), count }))
  }, [activeAnalyses, issueCategoryNameByCode])
  const issueRows = useMemo(() => {
    const counts = activeAnalyses.reduce<Record<string, { count: number; confidenceTotal: number; departments: Set<string> }>>(
      (totals, analysis) => {
        const primaryPrediction = analysis.issue_category_predictions.find((prediction) => prediction.is_primary)
        if (!primaryPrediction) {
          return totals
        }
        totals[primaryPrediction.category_code] ??= {
          count: 0,
          confidenceTotal: 0,
          departments: new Set<string>(),
        }
        totals[primaryPrediction.category_code].count += 1
        totals[primaryPrediction.category_code].confidenceTotal += primaryPrediction.confidence
        totals[primaryPrediction.category_code].departments.add(primaryPrediction.department_code)
        return totals
      },
      {}
    )
    return Object.entries(counts)
      .sort((a, b) => b[1].count - a[1].count)
      .map(([categoryCode, values]) => ({
        categoryCode,
        categoryName: issueCategoryNameByCode[categoryCode] ?? categoryCode.replaceAll("_", " "),
        count: values.count,
        averageConfidence: values.confidenceTotal / values.count,
        departments: Array.from(values.departments),
      }))
  }, [activeAnalyses, issueCategoryNameByCode])
  const semanticClusters = semanticAnalysis?.clusters ?? []
  const nearDuplicatePairCount = semanticAnalysis?.near_duplicate_pairs.length ?? 0
  const scopedDepartmentName = scopedDepartments.find((department) => department.code === effectiveDepartmentCode)?.name

  const loadIngestionData = useCallback(async () => {
    setError(null)
    const reviewsUrl = new URL(`${apiBaseUrl}/reviews`)
    const semanticUrl = new URL(`${apiBaseUrl}/analysis/semantic-clusters`)
    const overviewUrl = new URL(`${apiBaseUrl}/overview/kpis`)
    if (issueCategoryFilter !== "all") {
      reviewsUrl.searchParams.set("issue_category_code", issueCategoryFilter)
      semanticUrl.searchParams.set("issue_category_code", issueCategoryFilter)
      overviewUrl.searchParams.set("issue_category_code", issueCategoryFilter)
    }
    if (departmentFilter !== "all") {
      reviewsUrl.searchParams.set("department_code", departmentFilter)
      semanticUrl.searchParams.set("department_code", departmentFilter)
      overviewUrl.searchParams.set("department_code", departmentFilter)
    } else if (effectiveDepartmentCode) {
      reviewsUrl.searchParams.set("department_code", effectiveDepartmentCode)
      semanticUrl.searchParams.set("department_code", effectiveDepartmentCode)
      overviewUrl.searchParams.set("department_code", effectiveDepartmentCode)
    }
    const [reviewsResponse, semanticResponse, overviewResponse, runsResponse, sourceStatusResponse, configResponse] = await Promise.all([
      fetch(reviewsUrl),
      fetch(semanticUrl),
      fetch(overviewUrl),
      fetch(`${apiBaseUrl}/ingestion/runs`),
      fetch(`${apiBaseUrl}/ingestion/source-status`),
      fetch(`${apiBaseUrl}/config`),
    ])
    if (!reviewsResponse.ok || !semanticResponse.ok || !overviewResponse.ok || !runsResponse.ok || !sourceStatusResponse.ok || !configResponse.ok) {
      throw new Error("Unable to load review ingestion data")
    }
    const reviewsPayload = await reviewsResponse.json()
    const semanticPayload = await semanticResponse.json()
    const overviewPayload = await overviewResponse.json()
    const runsPayload = await runsResponse.json()
    const sourceStatusPayload = await sourceStatusResponse.json()
    const configPayload = await configResponse.json()
    setReviews(reviewsPayload.reviews)
    setSemanticAnalysis(semanticPayload)
    setOverviewKpi(overviewPayload)
    setRuns(runsPayload.runs)
    setSourceStatuses(sourceStatusPayload.sources)
    setIssueCategories(configPayload.issue_categories)
    setDepartments(configPayload.departments)
  }, [departmentFilter, effectiveDepartmentCode, issueCategoryFilter])

  useEffect(() => {
    setIsLoading(true)
    loadIngestionData()
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Unable to load data"))
      .finally(() => setIsLoading(false))
  }, [loadIngestionData])

  async function triggerConnectorImport(connectorKey: string) {
    setImportingConnector(connectorKey)
    setError(null)
    try {
      const response = await fetch(`${apiBaseUrl}/ingestion/connectors/${connectorKey}`, { method: "POST" })
      if (!response.ok) {
        throw new Error(`${connectorKey} import failed`)
      }
      await loadIngestionData()
    } catch (importError) {
      setError(importError instanceof Error ? importError.message : `${connectorKey} import failed`)
    } finally {
      setImportingConnector(null)
    }
  }

  async function triggerReanalysis() {
    setIsReanalyzing(true)
    setError(null)
    try {
      const response = await fetch(`${apiBaseUrl}/analysis/reanalyze`, { method: "POST" })
      if (!response.ok) {
        throw new Error("Reanalysis failed")
      }
      await loadIngestionData()
    } catch (analysisError) {
      setError(analysisError instanceof Error ? analysisError.message : "Reanalysis failed")
    } finally {
      setIsReanalyzing(false)
    }
  }

  return (
    <SidebarProvider
      style={
        {
          "--sidebar-width": "calc(var(--spacing) * 72)",
          "--header-height": "calc(var(--spacing) * 12)",
        } as React.CSSProperties
      }
    >
      <AppSidebar variant="inset" />
      <SidebarInset>
        <SiteHeader />
        <main className="flex flex-1 flex-col gap-6 p-4 md:p-6">
          <section className="grid gap-4 lg:grid-cols-[1.25fr_0.75fr]">
            <div className="rounded-lg border bg-card p-6 shadow-sm">
              <Badge variant="outline" className="mb-4">
                Kingsbury case study
              </Badge>
              <h2 className="max-w-3xl text-3xl font-semibold tracking-tight">
                Guest review intelligence and action management
              </h2>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
                A focused dashboard shell for reviewing verified guest feedback,
                spotting recurring service issues, and turning priority findings
                into department-owned action tickets.
              </p>
              {activeRole && (
                <div className="mt-4 flex flex-wrap gap-2">
                  <Badge variant="outline" className="text-xs">{activeRole.name}</Badge>
                  <Badge variant="secondary" className="text-xs">{scopeLabel}</Badge>
                  <Badge variant="outline" className="text-xs">{workflowLabel}</Badge>
                  {effectiveDepartmentCode && departmentFilter === "all" && scopedDepartmentName && (
                    <Badge variant="outline" className="text-xs">
                      Defaulting to {scopedDepartmentName}
                    </Badge>
                  )}
                </div>
              )}
            </div>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Source policy</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-muted-foreground">
                <p>MVP KPIs use Google Business Profile, Booking.com, and Tripadvisor review-platform connectors.</p>
                <p>Connector runs keep source identity and ingestion audit history for each platform.</p>
              </CardContent>
            </Card>
          </section>

          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {importedMetrics.map((metric) => (
              <Card key={metric.label}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    {metric.label}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-semibold">{metric.value}</div>
                  <p className="mt-1 text-xs text-muted-foreground">{metric.detail}</p>
                </CardContent>
              </Card>
            ))}
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Sentiment analysis</CardTitle>
              </CardHeader>
              <CardContent>
                <ChartContainer config={sentimentConfig} className="h-72 w-full">
                  <BarChart data={sentimentData}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="sentiment" tickLine={false} axisLine={false} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Bar dataKey="reviews" fill="var(--color-reviews)" radius={6} />
                  </BarChart>
                </ChartContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Issue categories</CardTitle>
              </CardHeader>
              <CardContent>
                <ChartContainer config={issueConfig} className="h-72 w-full">
                  <BarChart data={issueData}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="category" tickLine={false} axisLine={false} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Bar dataKey="count" fill="var(--color-count)" radius={6} />
                  </BarChart>
                </ChartContainer>
              </CardContent>
            </Card>
          </section>

          <Card id="issues">
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle>Issue category predictions</CardTitle>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Primary multi-label predictions grouped by operational category and routed department.
                  </p>
                </div>
                <Badge variant="outline">{issueRows.length} active categories</Badge>
              </div>
            </CardHeader>
            <CardContent>
              {issueRows.length === 0 ? (
                <p className="text-sm text-muted-foreground">Run an import or refresh analysis to populate issue predictions.</p>
              ) : (
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {issueRows.map((issue) => (
                    <div key={issue.categoryCode} className="rounded-lg border p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-medium">{issue.categoryName}</p>
                          <p className="text-xs text-muted-foreground">{issue.count} reviews matched</p>
                        </div>
                        <Badge variant="secondary">{Math.round(issue.averageConfidence * 100)}%</Badge>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {issue.departments.map((departmentCode) => (
                          <Badge key={departmentCode} variant="outline">
                            {departmentNameByCode[departmentCode] ?? departmentCode.replaceAll("_", " ")}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle>Semantic issue clusters</CardTitle>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Local embedding similarity groups near-duplicate reviews for visibility without merging records.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">{semanticClusters.length} clusters</Badge>
                  <Badge variant="secondary">{nearDuplicatePairCount} near-duplicate pairs</Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {semanticClusters.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No semantic clusters above the current similarity threshold.
                </p>
              ) : (
                <div className="grid gap-3 lg:grid-cols-2">
                  {semanticClusters.map((cluster) => (
                    <div key={cluster.cluster_id} className="rounded-lg border p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="font-medium">
                            {issueCategoryNameByCode[cluster.category_code] ?? cluster.category_code.replaceAll("_", " ")}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {cluster.size} reviews · representative #{cluster.representative_review_id}
                          </p>
                        </div>
                        <Badge variant="secondary">{Math.round(cluster.average_similarity * 100)}% similar</Badge>
                      </div>
                      <p className="mt-3 line-clamp-2 text-sm text-muted-foreground">{cluster.representative_text}</p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Badge variant="outline">
                          {departmentNameByCode[cluster.department_code] ?? cluster.department_code.replaceAll("_", " ")}
                        </Badge>
                        {Object.entries(cluster.source_mix).map(([sourceCode, count]) => (
                          <Badge key={sourceCode} variant="outline">
                            {sourceCode.replaceAll("_", " ")}: {count}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <section className="grid gap-4 xl:grid-cols-4">
            {queues.map((queue) => (
              <Card key={queue.title}>
                <CardHeader>
                  <div className="flex items-center justify-between gap-3">
                    <CardTitle>{queue.title}</CardTitle>
                    <Badge variant="secondary">{queue.status}</Badge>
                  </div>
                </CardHeader>
                <CardContent className="text-sm leading-6 text-muted-foreground">
                  {queue.body}
                </CardContent>
              </Card>
            ))}
          </section>

          <section id="ingestion" className="grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <CardTitle>Verified source imports</CardTitle>
                  <div className="flex flex-wrap gap-2">
                    <Button onClick={triggerReanalysis} disabled={isReanalyzing} variant="outline">
                      {isReanalyzing ? "Reanalyzing" : "Refresh analysis"}
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                {error ? <p className="text-destructive">{error}</p> : null}
                {isLoading ? (
                  <p className="text-muted-foreground">Loading ingestion status.</p>
                ) : verifiedSourceStatuses.length > 0 ? (
                  <div className="space-y-3">
                    {verifiedSourceStatuses.map((source) => {
                      const run = source.latest_run
                      const connectorKey = source.connector_key ?? ""
                      const hasErrors = source.errors.length > 0
                      return (
                        <div key={source.source_code} className="rounded-md border p-3">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <p className="font-medium">{source.source_name}</p>
                              <p className="text-xs text-muted-foreground">{connectorKey}</p>
                            </div>
                            <div className="flex items-center gap-2">
                              <Badge variant={run?.status === "completed" ? "secondary" : hasErrors ? "destructive" : "outline"}>
                                {run?.status ?? "not run"}
                              </Badge>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => triggerConnectorImport(connectorKey)}
                                disabled={importingConnector === connectorKey}
                              >
                                {importingConnector === connectorKey ? "Importing" : "Run"}
                              </Button>
                            </div>
                          </div>
                          {run ? (
                            <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
                              <p>Completed: {formatDate(run.completed_at)}</p>
                              <p>
                                {run.records_seen} seen, {run.records_created} created, {run.records_updated} updated,{" "}
                                {run.records_skipped} skipped, {run.records_duplicate_flagged} duplicate flagged
                              </p>
                            </div>
                          ) : (
                            <p className="mt-3 text-xs text-muted-foreground">No import run recorded for this source.</p>
                          )}
                          {hasErrors ? (
                            <div className="mt-3 space-y-1 text-xs text-destructive">
                              {source.errors.map((sourceError) => (
                                <p key={sourceError}>{sourceError}</p>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <p className="text-muted-foreground">No ingestion runs yet.</p>
                )}
              </CardContent>
            </Card>

            <Card id="reviews">
              <CardHeader>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <CardTitle>Imported records</CardTitle>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Review records imported from the configured platform connectors.
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Select value={issueCategoryFilter} onValueChange={(value) => setIssueCategoryFilter(value ?? "all")}>
                      <SelectTrigger size="sm" className="min-w-44">
                        <SelectValue placeholder="Issue category" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All issue categories</SelectItem>
                        {issueCategories.map((category) => (
                          <SelectItem key={category.code} value={category.code}>
                            {category.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Select value={departmentFilter} onValueChange={(value) => setDepartmentFilter(value ?? "all")}>
                      <SelectTrigger size="sm" className="min-w-40">
                        <SelectValue placeholder="Department" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All departments</SelectItem>
                        {departments.map((department) => (
                          <SelectItem key={department.code} value={department.code}>
                            {department.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {reviews.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Run a review-platform connector import to populate normalized records.
                  </p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Review</TableHead>
                        <TableHead>Source</TableHead>
                        <TableHead>Rating</TableHead>
                        <TableHead>Sentiment</TableHead>
                        <TableHead>Category</TableHead>
                        <TableHead>Department</TableHead>
                        <TableHead>Severity</TableHead>
                        <TableHead>Analysis</TableHead>
                        <TableHead>Dedupe</TableHead>
                        <TableHead>Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {reviews.map((review) => (
                        <TableRow key={review.id}>
                          <TableCell className="min-w-80 whitespace-normal">
                            <div className="font-medium">{review.title ?? review.external_review_id}</div>
                            <div className="text-xs text-muted-foreground">
                              {review.reviewer_name ?? "Anonymous"} · {formatDate(review.review_date)}
                            </div>
                            <p className="mt-1 max-h-10 overflow-hidden text-sm text-muted-foreground">{review.body}</p>
                          </TableCell>
                          <TableCell>
                            <div className="font-medium">{review.source_name}</div>
                            <Badge variant="secondary">Review platform</Badge>
                          </TableCell>
                          <TableCell>{review.rating ?? "N/A"}</TableCell>
                          <TableCell>
                            <div className="font-medium">{review.analysis?.sentiment_label ?? review.sentiment_label}</div>
                            <div className="text-xs text-muted-foreground">
                              score {review.analysis?.sentiment_score.toFixed(2) ?? review.sentiment_score.toFixed(2)}
                            </div>
                          </TableCell>
                          <TableCell className="min-w-48">
                            <div className="flex flex-wrap gap-1">
                              {(review.analysis?.issue_category_predictions ?? []).slice(0, 3).map((prediction) => (
                                <Badge key={prediction.id} variant={prediction.is_primary ? "secondary" : "outline"}>
                                  {issueCategoryNameByCode[prediction.category_code] ?? prediction.category_code.replaceAll("_", " ")}{" "}
                                  {Math.round(prediction.confidence * 100)}%
                                </Badge>
                              ))}
                              {review.analysis?.issue_category_predictions.length ? null : review.issue_category_code}
                            </div>
                          </TableCell>
                          <TableCell>
                            {departmentNameByCode[review.analysis?.department_code ?? review.department_code] ??
                              (review.analysis?.department_code ?? review.department_code).replaceAll("_", " ")}
                          </TableCell>
                          <TableCell>
                            <Badge variant={["high", "critical"].includes(review.analysis?.severity_label ?? review.severity) ? "destructive" : "outline"}>
                              {review.analysis?.severity_label ?? review.severity}
                            </Badge>
                            <div className="mt-1 text-xs text-muted-foreground">
                              score {review.analysis?.severity_score ?? "N/A"}
                            </div>
                          </TableCell>
                          <TableCell className="min-w-48">
                            <div className="font-medium">{review.analysis?.analysis_version ?? "not analyzed"}</div>
                            <div className="text-xs text-muted-foreground">
                              {review.analysis?.model_version ?? "No model metadata"}
                            </div>
                            <div className="text-xs text-muted-foreground">
                              issue model {review.analysis?.issue_category_predictions[0]?.model_version ?? "N/A"}
                            </div>
                            <div className="text-xs text-muted-foreground">
                              recurrence {review.analysis?.explanation_factors.signals?.recurrence_count_7d ?? 0}
                            </div>
                          </TableCell>
                          <TableCell>
                            {review.is_content_duplicate ? <Badge variant="outline">Content duplicate</Badge> : "Unique"}
                          </TableCell>
                          <TableCell>{review.action_status}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </section>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
