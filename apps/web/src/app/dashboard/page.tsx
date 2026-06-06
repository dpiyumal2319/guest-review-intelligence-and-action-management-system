"use client"

import Image from "next/image"
import { Suspense, useCallback, useEffect, useMemo, useState } from "react"
import { AlertTriangleIcon, Building2Icon, ClipboardListIcon, TicketCheckIcon } from "lucide-react"

import { AppSidebar } from "@/components/app-sidebar"
import { DashboardFilterBar } from "@/components/dashboard-filter-bar"
import { SiteHeader } from "@/components/site-header"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { useDemoRole } from "@/hooks/use-demo-role"
import { useDashboardFilters } from "@/hooks/use-dashboard-filters"
import type {
  Department,
  IssueCategory,
  IssueSummary,
  IssueSummaryItem,
  OverviewKpi,
  Review,
  ReviewSource,
  SemanticAnalysis,
  SemanticIssueCluster,
} from "@/lib/api-types"
import type React from "react"

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

const platformLogos: Record<string, string> = {
  google_business_profile: "/logos/google-com-logo.png",
  booking_com: "/logos/booking-com-logo.png",
  tripadvisor: "/logos/tripadvisor-com-logo.png",
}

const riskOrder: Record<string, number> = {
  low: 1,
  medium: 2,
  high: 3,
  critical: 4,
}

function formatDate(value: string | null) {
  if (!value) {
    return "Not recorded"
  }
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value))
}

function formatCodeLabel(value: string) {
  return value.replaceAll("_", " ")
}

function sentimentVariant(label: string): "default" | "secondary" | "destructive" | "outline" {
  if (label === "positive") return "default"
  if (label === "negative") return "destructive"
  return "secondary"
}

function reputationRiskVariant(label: string): "default" | "secondary" | "destructive" | "outline" {
  if (label === "critical" || label === "high") return "destructive"
  if (label === "medium") return "secondary"
  return "outline"
}

function actionStatusVariant(label: string): "default" | "secondary" | "destructive" | "outline" {
  if (label === "new") return "destructive"
  if (label === "reviewed") return "secondary"
  if (label === "ticket_created") return "default"
  return "outline"
}

function ticketStateLabel(ticketIds: number[]) {
  if (ticketIds.length === 0) {
    return "Ticket needed"
  }
  if (ticketIds.length === 1) {
    return "1 ticket linked"
  }
  return `${ticketIds.length} tickets linked`
}

function evidenceForItem(item: IssueSummaryItem, clusters: SemanticIssueCluster[]) {
  return clusters.find(
    (cluster) => cluster.category_code === item.category_code && cluster.department_code === item.department_code
  )?.representative_text
}

function PlatformLogo({ sourceCode, sourceName }: { sourceCode: string; sourceName: string }) {
  const logo = platformLogos[sourceCode]

  if (!logo) {
    return <span className="text-xs text-muted-foreground">{sourceName}</span>
  }

  return (
    <span className="inline-flex items-center gap-2">
      <Image
        src={logo}
        alt={`${sourceName} logo`}
        width={18}
        height={18}
        className="size-4 rounded-sm object-contain"
      />
      <span className="text-xs text-muted-foreground">{sourceName}</span>
    </span>
  )
}

function PlatformSpread({
  sourceMix,
  sourceNameByCode,
}: {
  sourceMix: Record<string, number>
  sourceNameByCode: Record<string, string>
}) {
  const entries = Object.entries(sourceMix)

  if (entries.length === 0) {
    return <span className="text-xs text-muted-foreground">No platform signal</span>
  }

  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([sourceCode, count]) => {
        const sourceName = sourceNameByCode[sourceCode] ?? formatCodeLabel(sourceCode)
        return (
          <span key={sourceCode} className="inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs">
            {platformLogos[sourceCode] ? (
              <Image
                src={platformLogos[sourceCode]}
                alt={`${sourceName} logo`}
                width={16}
                height={16}
                className="size-3.5 rounded-sm object-contain"
              />
            ) : null}
            <span>{count}</span>
          </span>
        )
      })}
    </div>
  )
}

function UrgencyMetric({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string
  detail: string
}) {
  return (
    <Card size="sm">
      <CardContent className="grid gap-3">
        <div className="flex items-center justify-between gap-3">
          <span className="rounded-md bg-muted p-2">
            <Icon className="size-4 text-foreground" />
          </span>
          <span className="text-2xl font-semibold tabular-nums">{value}</span>
        </div>
        <div>
          <p className="text-sm font-medium">{label}</p>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{detail}</p>
        </div>
      </CardContent>
    </Card>
  )
}

function CompactSentiment({ mix, total }: { mix: Record<string, number>; total: number }) {
  const items = [
    { code: "negative", label: "Negative" },
    { code: "mixed", label: "Mixed" },
    { code: "positive", label: "Positive" },
  ]

  return (
    <div className="space-y-3">
      {items.map((item) => {
        const count = mix[item.code] ?? 0
        const width = total > 0 ? Math.round((count / total) * 100) : 0
        return (
          <div key={item.code} className="grid grid-cols-[5.5rem_1fr_2.5rem] items-center gap-3 text-xs">
            <span className="font-medium">{item.label}</span>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-foreground" style={{ width: `${width}%` }} />
            </div>
            <span className="text-right tabular-nums text-muted-foreground">{count}</span>
          </div>
        )
      })}
    </div>
  )
}

function OverviewContent() {
  const { filters, setFilter, clearFilters, buildApiParams, hasActiveFilters } = useDashboardFilters()
  const { activeRole, scopeLabel, workflowLabel } = useDemoRole()
  const [reviews, setReviews] = useState<Review[]>([])
  const [sources, setSources] = useState<ReviewSource[]>([])
  const [issueSummary, setIssueSummary] = useState<IssueSummary | null>(null)
  const [semanticAnalysis, setSemanticAnalysis] = useState<SemanticAnalysis | null>(null)
  const [overviewKpi, setOverviewKpi] = useState<OverviewKpi | null>(null)
  const [categories, setCategories] = useState<IssueCategory[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadConfig = useCallback(async () => {
    const res = await fetch(`${apiBaseUrl}/config`)
    if (!res.ok) {
      throw new Error("Failed to load filter configuration")
    }
    const data = await res.json()
    setSources(data.review_sources)
    setCategories(data.issue_categories)
    setDepartments(data.departments)
  }, [])

  const loadOverview = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const params = buildApiParams()
      const priorityParams = buildApiParams({ order_by: "operational_priority", per_page: "8" })

      const [reviewsRes, issueSummaryRes, semanticRes, kpiRes] = await Promise.all([
        fetch(`${apiBaseUrl}/reviews?${priorityParams}`),
        fetch(`${apiBaseUrl}/issues/summary?${params}`),
        fetch(`${apiBaseUrl}/analysis/semantic-clusters?${params}`),
        fetch(`${apiBaseUrl}/overview/kpis?${params}`),
      ])

      if (!reviewsRes.ok || !issueSummaryRes.ok || !semanticRes.ok || !kpiRes.ok) {
        throw new Error("Failed to load overview data")
      }

      const [reviewsData, issueSummaryData, semanticData, kpiData] = await Promise.all([
        reviewsRes.json(),
        issueSummaryRes.json(),
        semanticRes.json(),
        kpiRes.json(),
      ])

      setReviews(reviewsData.reviews)
      setIssueSummary(issueSummaryData)
      setSemanticAnalysis(semanticData)
      setOverviewKpi(kpiData)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load overview data")
    } finally {
      setIsLoading(false)
    }
  }, [buildApiParams])

  useEffect(() => {
    loadConfig().catch((loadError) => {
      setError(loadError instanceof Error ? loadError.message : "Failed to load filter configuration")
    })
  }, [loadConfig])

  useEffect(() => {
    loadOverview()
  }, [loadOverview])

  const categoryNameByCode = useMemo(
    () => Object.fromEntries(categories.map((category) => [category.code, category.name])),
    [categories]
  )
  const departmentNameByCode = useMemo(
    () => Object.fromEntries(departments.map((department) => [department.code, department.name])),
    [departments]
  )
  const sourceNameByCode = useMemo(
    () => Object.fromEntries(sources.map((source) => [source.code, source.name])),
    [sources]
  )

  const highRiskReviews =
    (overviewKpi?.reputation_risk_mix?.high ?? 0) + (overviewKpi?.reputation_risk_mix?.critical ?? 0)
  const ticketNeededReviews =
    (overviewKpi?.action_status_mix?.new ?? 0) + (overviewKpi?.action_status_mix?.reviewed ?? 0)
  const issuePressure = issueSummary?.items.slice(0, 5) ?? []
  const recurringRows = issuePressure.slice(0, 4)
  const highestRiskIssue = issuePressure[0]
  const topDepartment = overviewKpi?.top_departments?.[0]
  const totalReviews = overviewKpi?.total_reviews ?? 0

  const urgencyMetrics = [
    {
      icon: AlertTriangleIcon,
      label: "High Reputation Risk",
      value: isLoading ? "..." : highRiskReviews.toString(),
      detail: "High and critical reviews in the current operational view.",
    },
    {
      icon: TicketCheckIcon,
      label: "Ticket-needed reviews",
      value: isLoading ? "..." : ticketNeededReviews.toString(),
      detail: "New or reviewed guest feedback that has not become a corrective-action ticket.",
    },
    {
      icon: Building2Icon,
      label: "Primary owner pressure",
      value: isLoading
        ? "..."
        : topDepartment
          ? (departmentNameByCode[topDepartment.code] ?? formatCodeLabel(topDepartment.code))
          : "None",
      detail: topDepartment ? `${topDepartment.count} reviews currently route to this department.` : "No department signal yet.",
    },
    {
      icon: ClipboardListIcon,
      label: "Recurring issue groups",
      value: isLoading ? "..." : (issueSummary?.items.length ?? 0).toString(),
      detail: "Category and department groups that can become owned action work.",
    },
  ]

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
        <main className="flex flex-1 flex-col gap-5 p-4 md:p-6">
          <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline">Operations overview</Badge>
                {activeRole ? <Badge variant="secondary">{activeRole.name}</Badge> : null}
                {activeRole ? <Badge variant="outline">{scopeLabel}</Badge> : null}
                {activeRole ? <Badge variant="outline">{workflowLabel}</Badge> : null}
              </div>
              <div>
                <h1 className="max-w-3xl text-2xl font-semibold tracking-tight md:text-3xl">
                  What needs attention now
                </h1>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                  Prioritized Reputation Risk, recurring complaint pressure, and department-owned action needs for the current review view.
                </p>
              </div>
            </div>

            <Card size="sm">
              <CardHeader className="pb-1">
                <CardTitle className="text-sm">Platform scope</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-3">
                {sources.map((source) => (
                  <PlatformLogo key={source.code} sourceCode={source.code} sourceName={source.name} />
                ))}
              </CardContent>
            </Card>
          </section>

          <DashboardFilterBar
            filters={filters}
            onFilterChange={setFilter}
            onClear={clearFilters}
            hasActiveFilters={hasActiveFilters}
            sources={sources}
            departments={departments}
          />

          {error ? (
            <p className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}
            </p>
          ) : null}

          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {urgencyMetrics.map((metric) => (
              <UrgencyMetric key={metric.label} {...metric} />
            ))}
          </section>

          <section className="grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
            <Card>
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <CardTitle>Complaint pressure by owner</CardTitle>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Repeated issue groups ranked by recent volume and Reputation Risk.
                    </p>
                  </div>
                  <Badge variant="outline">{isLoading ? "..." : `${issuePressure.length} groups`}</Badge>
                </div>
              </CardHeader>
              <CardContent>
                {isLoading ? (
                  <p className="text-sm text-muted-foreground">Loading owner pressure...</p>
                ) : issuePressure.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No complaint pressure matches the current filters.</p>
                ) : (
                  <div className="divide-y">
                    {issuePressure.map((item) => (
                      <div key={item.group_key} className="grid gap-3 py-4 first:pt-0 last:pb-0 md:grid-cols-[1fr_auto]">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="font-medium">
                              {categoryNameByCode[item.category_code] ?? item.category_name}
                            </p>
                            <Badge variant={reputationRiskVariant(item.highest_reputation_risk)} className="text-xs">
                              {item.highest_reputation_risk} risk
                            </Badge>
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {departmentNameByCode[item.department_code] ?? formatCodeLabel(item.department_code)} owner, latest evidence {formatDate(item.latest_review_date)}
                          </p>
                        </div>
                        <div className="grid grid-cols-3 gap-3 text-right text-xs md:min-w-56">
                          <div>
                            <p className="font-semibold tabular-nums">{item.recent_review_count}</p>
                            <p className="text-muted-foreground">recent</p>
                          </div>
                          <div>
                            <p className="font-semibold tabular-nums">{item.review_count}</p>
                            <p className="text-muted-foreground">total</p>
                          </div>
                          <div>
                            <p className="font-semibold tabular-nums">{item.average_reputation_risk_score}</p>
                            <p className="text-muted-foreground">risk avg</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <CardTitle>Risk mix</CardTitle>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Compact signal for mood, risk score, and the highest issue group.
                    </p>
                  </div>
                  <Badge variant="outline">{isLoading ? "..." : `${totalReviews} reviews`}</Badge>
                </div>
              </CardHeader>
              <CardContent className="grid gap-5">
                <CompactSentiment mix={overviewKpi?.sentiment_mix ?? {}} total={totalReviews} />
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-lg bg-muted/50 p-3">
                    <p className="text-xs text-muted-foreground">Average Reputation Risk</p>
                    <p className="mt-1 text-2xl font-semibold tabular-nums">
                      {isLoading ? "..." : overviewKpi?.average_reputation_risk_score ?? 0}
                    </p>
                  </div>
                  <div className="rounded-lg bg-muted/50 p-3">
                    <p className="text-xs text-muted-foreground">Highest pressure group</p>
                    <p className="mt-1 truncate text-sm font-medium">
                      {highestRiskIssue
                        ? `${categoryNameByCode[highestRiskIssue.category_code] ?? highestRiskIssue.category_name}`
                        : "No group yet"}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {highestRiskIssue
                        ? departmentNameByCode[highestRiskIssue.department_code] ?? formatCodeLabel(highestRiskIssue.department_code)
                        : "No department owner"}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </section>

          <section className="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <Card>
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <CardTitle>Recurring issue actions</CardTitle>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Scannable groups with owner, evidence, platform spread, and ticket state.
                    </p>
                  </div>
                  <Badge variant="outline">{isLoading ? "..." : `${semanticAnalysis?.clusters.length ?? 0} semantic`}</Badge>
                </div>
              </CardHeader>
              <CardContent>
                {isLoading ? (
                  <p className="text-sm text-muted-foreground">Loading recurring issue actions...</p>
                ) : recurringRows.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No recurring issue actions match the current filters.</p>
                ) : (
                  <div className="space-y-4">
                    {recurringRows.map((item) => {
                      const evidence = evidenceForItem(item, semanticAnalysis?.clusters ?? [])
                      return (
                        <div key={item.group_key} className="rounded-lg border p-4">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="font-medium">
                                {categoryNameByCode[item.category_code] ?? item.category_name}
                              </p>
                              <p className="mt-1 text-xs text-muted-foreground">
                                {departmentNameByCode[item.department_code] ?? formatCodeLabel(item.department_code)} owner
                              </p>
                            </div>
                            <Badge variant={item.linked_ticket_ids.length > 0 ? "default" : "destructive"} className="text-xs">
                              {ticketStateLabel(item.linked_ticket_ids)}
                            </Badge>
                          </div>
                          <p className="mt-3 line-clamp-2 text-sm text-muted-foreground">
                            {evidence ?? "Open the Issues page to inspect representative review evidence for this group."}
                          </p>
                          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                            <div className="flex flex-wrap gap-2">
                              <Badge variant="outline" className="text-xs">{item.review_count} reviews</Badge>
                              <Badge variant={reputationRiskVariant(item.highest_reputation_risk)} className="text-xs">
                                {item.highest_reputation_risk} risk
                              </Badge>
                              <Badge variant="secondary" className="text-xs">{formatDate(item.latest_review_date)}</Badge>
                            </div>
                            <PlatformSpread sourceMix={item.source_mix} sourceNameByCode={sourceNameByCode} />
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <CardTitle>Priority review queue</CardTitle>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Ordered by Reputation Risk, ticket need, and recency.
                    </p>
                  </div>
                  <Badge variant="outline">{isLoading ? "..." : `${reviews.length} queued`}</Badge>
                </div>
              </CardHeader>
              <CardContent>
                {isLoading ? (
                  <p className="text-sm text-muted-foreground">Loading priority queue...</p>
                ) : reviews.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No reviews match the current filters.</p>
                ) : (
                  <div className="space-y-3">
                    {reviews.map((review) => (
                      <article key={review.id} className="rounded-lg border p-4">
                        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_12rem]">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge variant={reputationRiskVariant(review.reputation_risk)} className="text-xs">
                                {review.reputation_risk} Reputation Risk
                              </Badge>
                              <Badge variant={actionStatusVariant(review.action_status)} className="text-xs">
                                {formatCodeLabel(review.action_status)}
                              </Badge>
                              <Badge variant={sentimentVariant(review.sentiment_label)} className="text-xs">
                                {review.sentiment_label}
                              </Badge>
                            </div>
                            <h2 className="mt-3 truncate text-sm font-medium">
                              {review.display_title ?? review.display_external_review_id}
                            </h2>
                            <p className="mt-1 text-xs text-muted-foreground">
                              {review.display_reviewer_name ?? "Guest"} · {formatDate(review.review_date)}
                            </p>
                            <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">
                              {review.display_body}
                            </p>
                          </div>
                          <div className="grid content-start gap-3 text-xs">
                            <PlatformLogo sourceCode={review.source_code} sourceName={review.source_name} />
                            <div>
                              <p className="font-medium">
                                {departmentNameByCode[review.department_code] ?? formatCodeLabel(review.department_code)}
                              </p>
                              <p className="mt-1 text-muted-foreground">
                                {categoryNameByCode[review.issue_category_code] ?? formatCodeLabel(review.issue_category_code)}
                              </p>
                            </div>
                            <div className="rounded-md bg-muted/50 p-2">
                              <p className="text-muted-foreground">Priority basis</p>
                              <p className="mt-1 font-medium">
                                Risk {riskOrder[review.reputation_risk] ?? 1}/4, {review.action_status === "ticket_created" ? "ticket linked" : "ticket check needed"}
                              </p>
                            </div>
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </section>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

export default function DashboardPage() {
  return (
    <Suspense>
      <OverviewContent />
    </Suspense>
  )
}
