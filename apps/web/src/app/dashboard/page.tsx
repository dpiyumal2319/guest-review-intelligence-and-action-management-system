"use client"

import { Suspense, useCallback, useEffect, useMemo, useState } from "react"
import {
  Bar,
  BarChart,
  CartesianGrid,
  XAxis,
} from "recharts"

import { AppSidebar } from "@/components/app-sidebar"
import { DashboardFilterBar } from "@/components/dashboard-filter-bar"
import { SiteHeader } from "@/components/site-header"
import { Badge } from "@/components/ui/badge"
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
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { useDemoRole } from "@/hooks/use-demo-role"
import { useDashboardFilters } from "@/hooks/use-dashboard-filters"
import type {
  Department,
  IssueCategory,
  IssueSummary,
  OverviewKpi,
  Review,
  ReviewSource,
  SemanticAnalysis,
} from "@/lib/api-types"
import type React from "react"

const sentimentConfig = {
  reviews: {
    label: "Reviews",
    color: "var(--chart-1)",
  },
} satisfies ChartConfig

const issueConfig = {
  reviews: {
    label: "Reviews",
    color: "var(--chart-2)",
  },
} satisfies ChartConfig

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

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

function buildOperationalSummary(
  review: Review,
  categoryNameByCode: Record<string, string>,
  departmentNameByCode: Record<string, string>
) {
  const categoryName = categoryNameByCode[review.issue_category_code] ?? formatCodeLabel(review.issue_category_code)
  const departmentName = departmentNameByCode[review.department_code] ?? formatCodeLabel(review.department_code)
  const statusLabel = formatCodeLabel(review.action_status)

  return `Route to ${departmentName} for ${categoryName.toLowerCase()} follow-up. Reputation Risk is ${review.reputation_risk}. Review status is ${statusLabel}.`
}

function OverviewContent() {
  const { filters, setFilter, clearFilters, buildApiParams, hasActiveFilters } = useDashboardFilters()
  const { activeRole, departments: scopedDepartments, effectiveDepartmentCode, scopeLabel, workflowLabel } = useDemoRole()
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
      if (!params.get("department_code") && effectiveDepartmentCode) {
        params.set("department_code", effectiveDepartmentCode)
      }

      const [reviewsRes, issueSummaryRes, semanticRes, kpiRes] = await Promise.all([
        fetch(`${apiBaseUrl}/reviews?${params}`),
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
  }, [buildApiParams, effectiveDepartmentCode])

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
  const scopedDepartmentName = scopedDepartments.find((department) => department.code === effectiveDepartmentCode)?.name
  const priorityReviews = reviews.slice(0, 8)
  const recurringPatterns = semanticAnalysis?.clusters.slice(0, 4) ?? []
  const sentimentData = useMemo(
    () =>
      ["positive", "mixed", "negative"].map((sentiment) => ({
        sentiment,
        reviews: overviewKpi?.sentiment_mix?.[sentiment] ?? 0,
      })),
    [overviewKpi]
  )
  const issueData = useMemo(
    () =>
      (issueSummary?.items ?? [])
        .slice(0, 6)
        .map((item) => ({
          category: categoryNameByCode[item.category_code] ?? formatCodeLabel(item.category_code),
          reviews: item.review_count,
        })),
    [categoryNameByCode, issueSummary]
  )
  const summaryCards = useMemo(() => {
    const totalReviews = overviewKpi?.total_reviews ?? 0
    const negativeReviews = overviewKpi?.sentiment_mix?.negative ?? 0
    const highRiskReviews = (overviewKpi?.reputation_risk_mix?.high ?? 0) + (overviewKpi?.reputation_risk_mix?.critical ?? 0)
    const topDepartment = overviewKpi?.top_departments?.[0]

    return [
      {
        label: "Reviews in scope",
        value: totalReviews.toString(),
        detail: totalReviews === 0 ? "No reviews match the current filters." : "Filtered verified-review workload.",
      },
      {
        label: "Negative sentiment",
        value: negativeReviews.toString(),
        detail: "Reviews that may require service recovery.",
      },
      {
        label: "High Reputation Risk",
        value: highRiskReviews.toString(),
        detail: "High and critical reviews that need attention first.",
      },
      {
        label: "Top department queue",
        value: topDepartment
          ? (departmentNameByCode[topDepartment.code] ?? formatCodeLabel(topDepartment.code))
          : "N/A",
        detail: topDepartment ? `${topDepartment.count} reviews currently routed here.` : "No department pressure signal yet.",
      },
      {
        label: "Average rating",
        value: overviewKpi?.average_rating != null ? overviewKpi.average_rating.toFixed(2) : "N/A",
        detail: "Across Google Business Profile, Booking.com, and Tripadvisor.",
      },
    ]
  }, [departmentNameByCode, overviewKpi])

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
                Review operations overview
              </h2>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
                Track guest feedback by review platform, focus on the highest Reputation Risk work, and route follow-up to the right department.
              </p>
              {activeRole && (
                <div className="mt-4 flex flex-wrap gap-2">
                  <Badge variant="outline" className="text-xs">{activeRole.name}</Badge>
                  <Badge variant="secondary" className="text-xs">{scopeLabel}</Badge>
                  <Badge variant="outline" className="text-xs">{workflowLabel}</Badge>
                  {effectiveDepartmentCode && !filters.department_code && scopedDepartmentName && (
                    <Badge variant="outline" className="text-xs">
                      Defaulting to {scopedDepartmentName}
                    </Badge>
                  )}
                </div>
              )}
            </div>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Review platforms in scope</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-muted-foreground">
                <p>Overview and queues are limited to verified guest-review platforms used in the demo.</p>
                <div className="flex flex-wrap gap-2">
                  {sources.map((source) => (
                    <Badge key={source.code} variant="outline">
                      {source.name}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          </section>

          <DashboardFilterBar
            filters={filters}
            onFilterChange={setFilter}
            onClear={clearFilters}
            hasActiveFilters={hasActiveFilters}
            sources={sources}
            categories={categories}
            departments={departments}
          />

          {error ? (
            <p className="text-sm text-destructive">{error}</p>
          ) : null}

          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            {summaryCards.map((metric) => (
              <Card key={metric.label}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    {metric.label}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-semibold">{isLoading ? "…" : metric.value}</div>
                  <p className="mt-1 text-xs text-muted-foreground">{metric.detail}</p>
                </CardContent>
              </Card>
            ))}
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Sentiment mix</CardTitle>
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
                <CardTitle>Top operational categories</CardTitle>
              </CardHeader>
              <CardContent>
                <ChartContainer config={issueConfig} className="h-72 w-full">
                  <BarChart data={issueData}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="category" tickLine={false} axisLine={false} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Bar dataKey="reviews" fill="var(--color-reviews)" radius={6} />
                  </BarChart>
                </ChartContainer>
              </CardContent>
            </Card>
          </section>

          <section className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <CardTitle>Recurring service patterns</CardTitle>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Repeated guest complaints that suggest a broader operational issue.
                    </p>
                  </div>
                  <Badge variant="outline">
                    {isLoading ? "…" : `${semanticAnalysis?.clusters.length ?? 0} patterns`}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                {isLoading ? (
                  <p className="text-sm text-muted-foreground">Loading recurring patterns…</p>
                ) : recurringPatterns.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No recurring patterns match the current filters.</p>
                ) : (
                  <div className="space-y-3">
                    {recurringPatterns.map((cluster) => (
                      <div key={cluster.cluster_id} className="rounded-lg border p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="font-medium">
                              {categoryNameByCode[cluster.category_code] ?? formatCodeLabel(cluster.category_code)}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {cluster.size} reviews routed to{" "}
                              {departmentNameByCode[cluster.department_code] ?? formatCodeLabel(cluster.department_code)}
                            </p>
                          </div>
                          <Badge variant="secondary">{cluster.size} related reviews</Badge>
                        </div>
                        <p className="mt-3 text-sm text-muted-foreground">{cluster.representative_text}</p>
                        <p className="mt-3 text-xs text-muted-foreground">
                          Seen across{" "}
                          {Object.entries(cluster.source_mix)
                            .map(([sourceCode, count]) => `${sourceNameByCode[sourceCode] ?? sourceCode}: ${count}`)
                            .join(", ")}
                        </p>
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
                    <CardTitle>Priority review queue</CardTitle>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Recent guest reviews with operational routing and action status.
                    </p>
                  </div>
                  <Badge variant="outline">
                    {isLoading ? "…" : `${reviews.length} reviews`}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                {isLoading ? (
                  <p className="text-sm text-muted-foreground">Loading review queue…</p>
                ) : priorityReviews.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No reviews match the current filters.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Review</TableHead>
                          <TableHead>Platform</TableHead>
                          <TableHead>Sentiment</TableHead>
                          <TableHead>Reputation Risk</TableHead>
                          <TableHead>Category</TableHead>
                          <TableHead>Department</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead>Operational note</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {priorityReviews.map((review) => (
                          <TableRow key={review.id}>
                            <TableCell className="min-w-72">
                              <div className="font-medium">{review.display_title ?? review.display_external_review_id}</div>
                              <div className="text-xs text-muted-foreground">
                                {review.display_reviewer_name ?? "Guest"} · {formatDate(review.review_date)}
                              </div>
                              <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{review.display_body}</p>
                            </TableCell>
                            <TableCell className="text-xs">{review.source_name}</TableCell>
                            <TableCell>
                              <Badge variant={sentimentVariant(review.sentiment_label)} className="text-xs">
                                {review.sentiment_label}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <Badge variant={reputationRiskVariant(review.reputation_risk)} className="text-xs">
                                {review.reputation_risk}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-xs">
                              {categoryNameByCode[review.issue_category_code] ?? formatCodeLabel(review.issue_category_code)}
                            </TableCell>
                            <TableCell className="text-xs">
                              {departmentNameByCode[review.department_code] ?? formatCodeLabel(review.department_code)}
                            </TableCell>
                            <TableCell className="text-xs">{formatCodeLabel(review.action_status)}</TableCell>
                            <TableCell className="min-w-72 text-xs text-muted-foreground">
                              {buildOperationalSummary(review, categoryNameByCode, departmentNameByCode)}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
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
