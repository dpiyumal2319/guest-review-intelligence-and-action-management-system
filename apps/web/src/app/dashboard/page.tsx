"use client"

import { useRouter } from "next/navigation"
import { Suspense, useCallback, useEffect, useMemo, useState } from "react"
import {
  AlertTriangleIcon,
  ClockIcon,
  ShieldAlertIcon,
  ShieldCheckIcon,
  SirenIcon,
  TrendingUpIcon,
} from "lucide-react"
import { Bar, BarChart, Cell, Pie, PieChart, XAxis, YAxis } from "recharts"

import { AppSidebar } from "@/components/app-sidebar"
import { DashboardFilterBar } from "@/components/dashboard-filter-bar"
import { SiteHeader } from "@/components/site-header"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useCountUp } from "@/hooks/use-count-up"
import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"
import { Skeleton } from "@/components/ui/skeleton"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { useDemoRole } from "@/hooks/use-demo-role"
import { useDashboardFilters } from "@/hooks/use-dashboard-filters"
import type {
  DashboardDrillThrough,
  Department,
  OverviewActionAnalytics,
  OverviewKpi,
  ReviewSource,
} from "@/lib/api-types"
import type React from "react"

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

// ─── Chart configs (stable references outside component) ─────────────────────

const sentimentConfig: ChartConfig = {
  positive: { label: "Positive", color: "#10b981" },
  mixed:    { label: "Mixed",    color: "#f59e0b" },
  negative: { label: "Negative", color: "#ef4444" },
}

const riskLevelConfig: ChartConfig = {
  low:      { label: "Low",      color: "#94a3b8" },
  medium:   { label: "Medium",   color: "#fcd34d" },
  high:     { label: "High",     color: "#f59e0b" },
  critical: { label: "Critical", color: "#ef4444" },
}

const deptConfig: ChartConfig = {
  count: { label: "Issues", color: "var(--chart-1)" },
}

const priorityConfig: ChartConfig = {
  count: { label: "Issues" },
}

const ownerConfig: ChartConfig = {
  active_issues:    { label: "Active Issues",    color: "var(--chart-1)" },
  high_risk_issues: { label: "High Risk Issues", color: "#ef4444" },
}

const platformConfig: ChartConfig = {
  high_risk_reviews: { label: "High Risk Reviews", color: "#ef4444" },
}

const PRIORITY_FILL: Record<string, string> = {
  urgent: "#ef4444",
  high:   "#f59e0b",
  medium: "#94a3b8",
  low:    "#cbd5e1",
}

const PRIORITY_ORDER: Record<string, number> = { urgent: 4, high: 3, medium: 2, low: 1 }

// ─── Helpers ─────────────────────────────────────────────────────────────────

function drillTo(router: ReturnType<typeof useRouter>, drill: DashboardDrillThrough) {
  const qs = new URLSearchParams(drill.filters).toString()
  router.push(qs ? `${drill.path}?${qs}` : drill.path)
}

function riskBadgeProps(score: number): {
  variant: "destructive" | "outline"
  className?: string
} {
  if (score >= 75) return { variant: "destructive" }
  if (score >= 50)
    return {
      variant: "outline",
      className:
        "border-amber-500 text-amber-700 bg-amber-50 dark:text-amber-400 dark:bg-amber-950/30",
    }
  return { variant: "outline" }
}

function statusBadgeVariant(
  status: string
): "destructive" | "secondary" | "outline" {
  if (status === "recurred") return "destructive"
  if (status === "active") return "secondary"
  return "outline"
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function DonutSkeleton() {
  return (
    <div className="flex items-center justify-center py-4">
      <div className="relative size-32">
        <Skeleton className="size-full rounded-full" />
        <div className="absolute inset-[26%] rounded-full bg-background" />
      </div>
    </div>
  )
}

function BarsSkeleton({ rows = 5 }: { rows?: number }) {
  const widths = [80, 60, 95, 70, 50, 85].slice(0, rows)
  return (
    <div className="space-y-2.5 py-2">
      {widths.map((w, i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton className="h-3 w-20 shrink-0" />
          <Skeleton className="h-5 rounded-sm" style={{ width: `${w}%` }} />
        </div>
      ))}
    </div>
  )
}

function DashboardSkeleton() {
  return (
    <>
      {/* KPI row */}
      <section className="grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Card key={i}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="size-4 rounded" />
            </CardHeader>
            <CardContent>
              <Skeleton className="mb-1.5 h-8 w-16" />
              <Skeleton className="h-3 w-20" />
            </CardContent>
          </Card>
        ))}
      </section>

      {/* Donut row */}
      <div className="grid gap-4 md:grid-cols-2">
        {[0, 1].map((i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-5 w-40" />
            </CardHeader>
            <CardContent>
              <DonutSkeleton />
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Bar chart row */}
      <div className="grid gap-4 md:grid-cols-2">
        {[0, 1].map((i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-5 w-36" />
            </CardHeader>
            <CardContent>
              <BarsSkeleton rows={i === 0 ? 5 : 4} />
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Owner Pressure skeleton */}
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-32" />
        </CardHeader>
        <CardContent>
          <BarsSkeleton rows={5} />
        </CardContent>
      </Card>
    </>
  )
}

// ─── Main content ─────────────────────────────────────────────────────────────

function DashboardContent() {
  const router = useRouter()
  const { filters, setFilter, clearFilters, buildApiParams, hasActiveFilters } =
    useDashboardFilters()
  const { activeRole, scopeLabel } = useDemoRole()
  const [kpis, setKpis] = useState<OverviewKpi | null>(null)
  const [analytics, setAnalytics] = useState<OverviewActionAnalytics | null>(null)
  const [sources, setSources] = useState<ReviewSource[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadConfig = useCallback(async () => {
    const res = await fetch(`${apiBaseUrl}/config`)
    if (!res.ok) return
    const data = await res.json()
    setSources(data.review_sources)
    setDepartments(data.departments)
  }, [])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = buildApiParams()
      const [kpiRes, analyticsRes] = await Promise.all([
        fetch(`${apiBaseUrl}/overview/kpis?${params}`),
        fetch(`${apiBaseUrl}/overview/action-analytics?${params}`),
      ])
      if (kpiRes.ok) setKpis(await kpiRes.json())
      if (analyticsRes.ok) setAnalytics(await analyticsRes.json())
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard")
    } finally {
      setLoading(false)
    }
  }, [buildApiParams])

  useEffect(() => { loadConfig() }, [loadConfig])
  useEffect(() => { loadData() }, [loadData])

  const departmentNameByCode = useMemo(
    () => Object.fromEntries(departments.map((d) => [d.code, d.name])),
    [departments]
  )
  const sourceNameByCode = useMemo(
    () => Object.fromEntries(sources.map((s) => [s.code, s.name])),
    [sources]
  )

  // ── Chart data ───────────────────────────────────────────────────────────

  const sentimentData = useMemo(() => {
    if (!kpis?.sentiment_mix) return []
    return (["positive", "mixed", "negative"] as const)
      .map((key) => ({
        name: key,
        value: kpis.sentiment_mix[key] ?? 0,
        fill: sentimentConfig[key]?.color as string,
      }))
      .filter((d) => d.value > 0)
  }, [kpis])

  const riskLevelData = useMemo(() => {
    if (!kpis?.reputation_risk_mix) return []
    return (["low", "medium", "high", "critical"] as const)
      .map((key) => ({
        name: key,
        value: kpis.reputation_risk_mix[key] ?? 0,
        fill: riskLevelConfig[key]?.color as string,
      }))
      .filter((d) => d.value > 0)
  }, [kpis])

  const deptChartData = useMemo(() => {
    if (!kpis?.department_issue_counts) return []
    return Object.entries(kpis.department_issue_counts)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 6)
      .map(([dept, count]) => ({
        name: departmentNameByCode[dept] ?? dept,
        count,
        dept,
      }))
  }, [kpis, departmentNameByCode])

  const priorityChartData = useMemo(() => {
    if (!kpis?.priority_distribution) return []
    return Object.entries(kpis.priority_distribution)
      .sort(([a], [b]) => (PRIORITY_ORDER[b] ?? 0) - (PRIORITY_ORDER[a] ?? 0))
      .map(([priority, count]) => ({
        priority,
        count,
        fill: PRIORITY_FILL[priority] ?? "#94a3b8",
      }))
  }, [kpis])

  const ownerChartData = useMemo(() => {
    if (!analytics?.owner_pressure) return []
    return analytics.owner_pressure.map((item) => ({
      name: departmentNameByCode[item.department_code] ?? item.department_code,
      active_issues: item.active_issues,
      high_risk_issues: item.high_risk_issues,
      issues_drill_through: item.issues_drill_through,
      reviews_drill_through: item.reviews_drill_through,
    }))
  }, [analytics, departmentNameByCode])

  const platformChartData = useMemo(() => {
    if (!analytics?.platform_risk_spread) return []
    return analytics.platform_risk_spread.map((item) => ({
      name: sourceNameByCode[item.source_code] ?? item.source_code,
      high_risk_reviews: item.high_risk_reviews,
      drill_through: item.drill_through,
    }))
  }, [analytics, sourceNameByCode])

  const ownerChartHeight = Math.max(200, ownerChartData.length * 56)
  const platformChartHeight = Math.max(140, platformChartData.length * 52)

  // ── Counted KPI values ───────────────────────────────────────────────────
  const countActiveIssues   = useCountUp(kpis?.active_issues ?? 0)
  const countHighRisk       = useCountUp(kpis?.high_risk_issues ?? 0)
  const countRecurred       = useCountUp(kpis?.recurred_issues ?? 0)
  const countTotalReviews   = useCountUp(kpis?.total_reviews ?? 0)
  const countAvgRisk        = useCountUp(kpis?.average_reputation_risk_score ?? 0)
  const countUntracked      = useCountUp(analytics?.action_leakage.review_count ?? 0)

  // ── Render ───────────────────────────────────────────────────────────────

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
        <main className="flex flex-1 flex-col gap-4 p-4 md:p-6">

          {/* Header */}
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
              <p className="mt-0.5 text-sm text-muted-foreground">
                Hotel guest review intelligence.
                {activeRole && (
                  <span className="ml-2 inline-flex items-center gap-1.5">
                    <Badge variant="outline" className="text-xs">{activeRole.name}</Badge>
                    <Badge variant="secondary" className="text-xs">{scopeLabel}</Badge>
                  </span>
                )}
              </p>
            </div>
          </div>

          <DashboardFilterBar
            filters={filters}
            onFilterChange={setFilter}
            onClear={clearFilters}
            hasActiveFilters={hasActiveFilters}
            sources={sources}
            departments={departments}
            showRiskGroup
          />

          {loading ? (
            <DashboardSkeleton />
          ) : error ? (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3">
              <p className="text-sm text-destructive">{error}</p>
              <button
                onClick={loadData}
                className="mt-2 text-xs text-destructive underline-offset-2 hover:underline"
              >
                Retry
              </button>
            </div>
          ) : kpis ? (
            <>
              {/* ── KPI Cards ─────────────────────────────────────────── */}
              <section className="grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-5">
                <Card
                  className={analytics ? "cursor-pointer transition-colors hover:bg-muted/50" : undefined}
                  style={{ animation: "card-enter 350ms ease-out both", animationDelay: "0ms" }}
                  onClick={() => analytics && drillTo(router, analytics.active_issues.drill_through)}
                >
                  <CardHeader className="flex flex-row items-center justify-between pb-2">
                    <CardTitle className="text-sm font-medium">Active Issues</CardTitle>
                    <SirenIcon className="size-4 text-amber-500" />
                  </CardHeader>
                  <CardContent>
                    <div className="tabular-nums text-2xl font-bold">{countActiveIssues}</div>
                    <p className="text-xs text-muted-foreground">{countRecurred} recurred</p>
                  </CardContent>
                </Card>

                <Card
                  className={analytics ? "cursor-pointer transition-colors hover:bg-muted/50" : undefined}
                  style={{ animation: "card-enter 350ms ease-out both", animationDelay: "50ms" }}
                  onClick={() => analytics && drillTo(router, analytics.high_risk_issues.drill_through)}
                >
                  <CardHeader className="flex flex-row items-center justify-between pb-2">
                    <CardTitle className="text-sm font-medium">High Risk Issues</CardTitle>
                    <AlertTriangleIcon className="size-4 text-destructive" />
                  </CardHeader>
                  <CardContent>
                    <div className="tabular-nums text-2xl font-bold">{countHighRisk}</div>
                    <p className="text-xs text-muted-foreground">Risk score ≥ 50</p>
                  </CardContent>
                </Card>

                <Card
                  style={{ animation: "card-enter 350ms ease-out both", animationDelay: "100ms" }}
                >
                  <CardHeader className="flex flex-row items-center justify-between pb-2">
                    <CardTitle className="text-sm font-medium">Total Reviews</CardTitle>
                    <ClockIcon className="size-4 text-muted-foreground" />
                  </CardHeader>
                  <CardContent>
                    <div className="tabular-nums text-2xl font-bold">{countTotalReviews}</div>
                    <p className="text-xs text-muted-foreground">
                      Avg rating: {kpis.average_rating?.toFixed(1) ?? "—"}
                    </p>
                  </CardContent>
                </Card>

                <Card
                  style={{ animation: "card-enter 350ms ease-out both", animationDelay: "150ms" }}
                >
                  <CardHeader className="flex flex-row items-center justify-between pb-2">
                    <CardTitle className="text-sm font-medium">Avg Risk Score</CardTitle>
                    <TrendingUpIcon className="size-4 text-muted-foreground" />
                  </CardHeader>
                  <CardContent>
                    <div className="tabular-nums text-2xl font-bold">
                      {countAvgRisk}
                    </div>
                    <p className="text-xs text-muted-foreground">0–100 across reviews</p>
                  </CardContent>
                </Card>

                {analytics && (
                  <Card
                    className={
                      analytics.action_leakage.review_count > 0
                        ? "cursor-pointer transition-colors hover:bg-muted/50"
                        : undefined
                    }
                    style={{ animation: "card-enter 350ms ease-out both", animationDelay: "200ms" }}
                    onClick={() =>
                      analytics.action_leakage.review_count > 0
                        ? drillTo(router, analytics.action_leakage.drill_through)
                        : undefined
                    }
                  >
                    <CardHeader className="flex flex-row items-center justify-between pb-2">
                      <CardTitle className="text-sm font-medium">Untracked Risk</CardTitle>
                      {analytics.action_leakage.review_count > 0 ? (
                        <ShieldAlertIcon className="size-4 text-amber-500" />
                      ) : (
                        <ShieldCheckIcon className="size-4 text-emerald-500" />
                      )}
                    </CardHeader>
                    <CardContent>
                      {analytics.action_leakage.review_count > 0 ? (
                        <>
                          <div className="tabular-nums text-2xl font-bold">
                            {countUntracked}
                          </div>
                          <p className="text-xs text-muted-foreground">
                            High-risk reviews, no linked issue
                          </p>
                        </>
                      ) : (
                        <>
                          <div className="tabular-nums text-2xl font-bold text-emerald-600 dark:text-emerald-400">
                            0
                          </div>
                          <p className="text-xs text-muted-foreground">No untracked risk</p>
                        </>
                      )}
                    </CardContent>
                  </Card>
                )}
              </section>

              {/* ── Donut Charts: Sentiment Mix + Risk Level ───────────── */}
              <div className="grid gap-4 md:grid-cols-2" style={{ animation: "fade-in 400ms ease-out both", animationDelay: "320ms" }}>
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Sentiment Mix</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {sentimentData.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No review data</p>
                    ) : (
                      <ChartContainer
                        config={sentimentConfig}
                        className="mx-auto aspect-square max-h-[260px]"
                      >
                        <PieChart>
                          <ChartTooltip
                            content={<ChartTooltipContent hideLabel nameKey="name" />}
                          />
                          <Pie
                            data={sentimentData}
                            dataKey="value"
                            nameKey="name"
                            innerRadius="55%"
                            paddingAngle={2}
                            strokeWidth={0}
                          >
                            {sentimentData.map((entry) => (
                              <Cell key={entry.name} fill={entry.fill} />
                            ))}
                          </Pie>
                          <ChartLegend content={<ChartLegendContent nameKey="name" />} />
                        </PieChart>
                      </ChartContainer>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Risk Level Distribution</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {riskLevelData.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No review data</p>
                    ) : (
                      <ChartContainer
                        config={riskLevelConfig}
                        className="mx-auto aspect-square max-h-[260px]"
                      >
                        <PieChart>
                          <ChartTooltip
                            content={<ChartTooltipContent hideLabel nameKey="name" />}
                          />
                          <Pie
                            data={riskLevelData}
                            dataKey="value"
                            nameKey="name"
                            innerRadius="55%"
                            paddingAngle={2}
                            strokeWidth={0}
                          >
                            {riskLevelData.map((entry) => (
                              <Cell key={entry.name} fill={entry.fill} />
                            ))}
                          </Pie>
                          <ChartLegend content={<ChartLegendContent nameKey="name" />} />
                        </PieChart>
                      </ChartContainer>
                    )}
                  </CardContent>
                </Card>
              </div>

              {/* ── Horizontal Bar Charts: Dept Issues + Priority ─────── */}
              <div className="grid gap-4 md:grid-cols-2" style={{ animation: "fade-in 400ms ease-out both", animationDelay: "400ms" }}>
                <Card className="flex flex-col">
                  <CardHeader>
                    <CardTitle className="text-base">Department Issues</CardTitle>
                  </CardHeader>
                  <CardContent className="flex-1">
                    {deptChartData.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No issues in this period</p>
                    ) : (
                      <ChartContainer
                        config={deptConfig}
                        className="aspect-auto h-[220px]"
                      >
                        <BarChart
                          data={deptChartData}
                          layout="vertical"
                          margin={{ top: 0, right: 12, bottom: 0, left: 0 }}
                        >
                          <YAxis
                            type="category"
                            dataKey="name"
                            width={112}
                            tick={{ fontSize: 11 }}
                            tickLine={false}
                            axisLine={false}
                          />
                          <XAxis type="number" hide />
                          <ChartTooltip content={<ChartTooltipContent />} />
                          <Bar
                            dataKey="count"
                            fill="var(--color-count)"
                            radius={[0, 4, 4, 0]}
                            cursor="pointer"
                            // eslint-disable-next-line @typescript-eslint/no-explicit-any
                            onClick={(entry: any) => {
                              const ownerItem = analytics?.owner_pressure.find(
                                (p) => p.department_code === entry.dept
                              )
                              if (ownerItem) drillTo(router, ownerItem.issues_drill_through)
                              else router.push(`/issues?department_code=${entry.dept}`)
                            }}
                          />
                        </BarChart>
                      </ChartContainer>
                    )}
                  </CardContent>
                </Card>

                <Card className="flex flex-col">
                  <CardHeader>
                    <CardTitle className="text-base">Priority Distribution</CardTitle>
                  </CardHeader>
                  <CardContent className="flex-1">
                    {priorityChartData.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No issues in this period</p>
                    ) : (
                      <ChartContainer
                        config={priorityConfig}
                        className="aspect-auto h-[190px]"
                      >
                        <BarChart
                          data={priorityChartData}
                          layout="vertical"
                          margin={{ top: 0, right: 12, bottom: 0, left: 0 }}
                        >
                          <YAxis
                            type="category"
                            dataKey="priority"
                            width={60}
                            tick={{ fontSize: 11 }}
                            tickLine={false}
                            axisLine={false}
                          />
                          <XAxis type="number" hide />
                          <ChartTooltip content={<ChartTooltipContent />} />
                          <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                            {priorityChartData.map((entry) => (
                              <Cell key={entry.priority} fill={entry.fill} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ChartContainer>
                    )}
                  </CardContent>
                </Card>
              </div>

              {analytics && (
                <>
                  {/* ── Owner Pressure — grouped horizontal bar chart ──── */}
                  <Card style={{ animation: "fade-in 400ms ease-out both", animationDelay: "480ms" }}>
                    <CardHeader>
                      <CardTitle className="text-base">Owner Pressure</CardTitle>
                    </CardHeader>
                    <CardContent>
                      {ownerChartData.length === 0 ? (
                        <p className="text-sm text-muted-foreground">No active issues</p>
                      ) : (
                        <ChartContainer
                          config={ownerConfig}
                          className="aspect-auto w-full"
                          style={{ height: ownerChartHeight }}
                        >
                          <BarChart
                            data={ownerChartData}
                            layout="vertical"
                            margin={{ top: 0, right: 12, bottom: 0, left: 0 }}
                            barCategoryGap="28%"
                          >
                            <YAxis
                              type="category"
                              dataKey="name"
                              width={130}
                              tick={{ fontSize: 11 }}
                              tickLine={false}
                              axisLine={false}
                            />
                            <XAxis type="number" hide />
                            <ChartTooltip
                              content={<ChartTooltipContent indicator="dot" />}
                            />
                            <ChartLegend content={<ChartLegendContent />} />
                            <Bar
                              dataKey="active_issues"
                              fill="var(--color-active_issues)"
                              radius={[0, 4, 4, 0]}
                              cursor="pointer"
                              // eslint-disable-next-line @typescript-eslint/no-explicit-any
                              onClick={(entry: any) => {
                                if (entry?.issues_drill_through)
                                  drillTo(router, entry.issues_drill_through)
                              }}
                            />
                            <Bar
                              dataKey="high_risk_issues"
                              fill="var(--color-high_risk_issues)"
                              radius={[0, 4, 4, 0]}
                              cursor="pointer"
                              // eslint-disable-next-line @typescript-eslint/no-explicit-any
                              onClick={(entry: any) => {
                                if (entry?.reviews_drill_through)
                                  drillTo(router, entry.reviews_drill_through)
                              }}
                            />
                          </BarChart>
                        </ChartContainer>
                      )}
                    </CardContent>
                  </Card>

                  {/* ── Platform Risk + Recent Issues ─────────────────── */}
                  <div className="grid gap-4 md:grid-cols-2" style={{ animation: "fade-in 400ms ease-out both", animationDelay: "560ms" }}>
                    <Card>
                      <CardHeader>
                        <CardTitle className="text-base">Platform Risk</CardTitle>
                      </CardHeader>
                      <CardContent>
                        {platformChartData.length === 0 ? (
                          <p className="text-sm text-muted-foreground">No platform data</p>
                        ) : (
                          <ChartContainer
                            config={platformConfig}
                            className="aspect-auto w-full"
                            style={{ height: platformChartHeight }}
                          >
                            <BarChart
                              data={platformChartData}
                              layout="vertical"
                              margin={{ top: 0, right: 12, bottom: 0, left: 0 }}
                            >
                              <YAxis
                                type="category"
                                dataKey="name"
                                width={140}
                                tick={{ fontSize: 11 }}
                                tickLine={false}
                                axisLine={false}
                              />
                              <XAxis type="number" hide />
                              <ChartTooltip content={<ChartTooltipContent />} />
                              <Bar
                                dataKey="high_risk_reviews"
                                fill="var(--color-high_risk_reviews)"
                                radius={[0, 4, 4, 0]}
                                cursor="pointer"
                                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                                onClick={(entry: any) => {
                                  if (entry?.drill_through)
                                    drillTo(router, entry.drill_through)
                                }}
                              />
                            </BarChart>
                          </ChartContainer>
                        )}
                      </CardContent>
                    </Card>

                    <Card>
                      <CardHeader>
                        <CardTitle className="text-base">Recent Issues</CardTitle>
                      </CardHeader>
                      <CardContent>
                        {analytics.recent_issues.length === 0 ? (
                          <p className="text-sm text-muted-foreground">No recent issues</p>
                        ) : (
                          <div className="space-y-3">
                            {analytics.recent_issues.map((issue) => {
                              const riskProps = riskBadgeProps(issue.reputation_risk_score)
                              return (
                                <div
                                  key={issue.issue_id}
                                  className="flex items-start justify-between gap-2"
                                >
                                  <div className="min-w-0">
                                    <button
                                      onClick={() =>
                                        drillTo(router, issue.issues_drill_through)
                                      }
                                      className="block max-w-[200px] truncate text-left text-sm font-medium hover:underline"
                                    >
                                      {issue.title}
                                    </button>
                                    <p className="text-xs text-muted-foreground">
                                      {departmentNameByCode[issue.department_code] ??
                                        issue.department_code}
                                    </p>
                                  </div>
                                  <div className="flex shrink-0 gap-1">
                                    <Badge
                                      variant={statusBadgeVariant(issue.status)}
                                      className="text-[10px]"
                                    >
                                      {issue.status}
                                    </Badge>
                                    <Badge
                                      variant={riskProps.variant}
                                      className={`text-[10px] tabular-nums ${riskProps.className ?? ""}`}
                                    >
                                      {issue.reputation_risk_score}
                                    </Badge>
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  </div>
                </>
              )}
            </>
          ) : null}
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

export default function DashboardPage() {
  return (
    <Suspense>
      <DashboardContent />
    </Suspense>
  )
}
