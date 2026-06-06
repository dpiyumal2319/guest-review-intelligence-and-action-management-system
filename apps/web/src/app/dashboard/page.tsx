"use client"

import Image from "next/image"
import Link from "next/link"
import { Suspense, useCallback, useEffect, useMemo, useState } from "react"
import { AlertTriangleIcon, ClockIcon, SirenIcon } from "lucide-react"

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
  OverviewKpi,
  OverviewActionAnalytics,
  ReviewSource,
} from "@/lib/api-types"
import type React from "react"

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

const platformLogos: Record<string, string> = {
  google_business_profile: "/logos/google-com-logo.png",
  booking_com: "/logos/booking-com-logo.png",
  tripadvisor: "/logos/tripadvisor-com-logo.png",
}

function riskBadgeVariant(score: number): "default" | "secondary" | "destructive" | "outline" {
  if (score >= 75) return "destructive"
  if (score >= 50) return "secondary"
  return "outline"
}

function statusBadgeVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "recurred") return "destructive"
  if (status === "active") return "secondary"
  return "outline"
}

function PlatformLogo({ sourceCode }: { sourceCode: string }) {
  const src = platformLogos[sourceCode]
  if (!src) return <span className="text-xs font-medium">{sourceCode}</span>
  return (
    <Image
      src={src}
      alt={sourceCode}
      width={16}
      height={16}
      className="size-4 object-contain opacity-80"
      unoptimized
    />
  )
}

function DashboardContent() {
  const { filters, setFilter, clearFilters, buildApiParams, hasActiveFilters } = useDashboardFilters()
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

  const departmentNameByCode = Object.fromEntries(departments.map((d) => [d.code, d.name]))
  const sourceNameByCode = Object.fromEntries(sources.map((s) => [s.code, s.name]))

  const priorityOrder: Record<string, number> = useMemo(() => ({ urgent: 4, high: 3, medium: 2, low: 1 }), [])

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
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
              <p className="text-sm text-muted-foreground">Hotel guest review intelligence dashboard.</p>
              {activeRole && (
                <div className="mt-2 flex flex-wrap gap-2">
                  <Badge variant="outline" className="text-xs">{activeRole.name}</Badge>
                  <Badge variant="secondary" className="text-xs">{scopeLabel}</Badge>
                </div>
              )}
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
            <p className="text-sm text-muted-foreground">Loading dashboard...</p>
          ) : error ? (
            <p className="text-sm text-destructive">{error}</p>
          ) : kpis ? (
            <>
              <section className="grid gap-4 md:grid-cols-4">
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between pb-2">
                    <CardTitle className="text-sm font-medium">Active Issues</CardTitle>
                    <SirenIcon className="size-4 text-amber-500" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">{kpis.active_issues}</div>
                    <p className="text-xs text-muted-foreground">
                      {kpis.recurred_issues} recurred
                    </p>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between pb-2">
                    <CardTitle className="text-sm font-medium">High Risk Issues</CardTitle>
                    <AlertTriangleIcon className="size-4 text-destructive" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">{kpis.high_risk_issues}</div>
                    <p className="text-xs text-muted-foreground">Risk score {">="} 50</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between pb-2">
                    <CardTitle className="text-sm font-medium">Total Reviews</CardTitle>
                    <ClockIcon className="size-4 text-muted-foreground" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">{kpis.total_reviews}</div>
                    <p className="text-xs text-muted-foreground">
                      Avg rating: {kpis.average_rating?.toFixed(1) ?? "\u2014"}
                    </p>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between pb-2">
                    <CardTitle className="text-sm font-medium">Avg Risk Score</CardTitle>
                    <AlertTriangleIcon className="size-4 text-muted-foreground" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">{kpis.average_reputation_risk_score}</div>
                    <p className="text-xs text-muted-foreground">Across all reviews</p>
                  </CardContent>
                </Card>
              </section>

              <div className="grid gap-4 md:grid-cols-2">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Department Issues</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      {Object.entries(kpis.department_issue_counts)
                        .sort(([, a], [, b]) => b - a)
                        .slice(0, 6)
                        .map(([dept, count]) => (
                          <div key={dept} className="flex items-center justify-between">
                            <span className="text-sm">{departmentNameByCode[dept] ?? dept}</span>
                            <Badge variant="outline">{count} issues</Badge>
                          </div>
                        ))}
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Priority Distribution</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      {Object.entries(kpis.priority_distribution)
                        .sort(([a], [b]) => (priorityOrder[b] ?? 0) - (priorityOrder[a] ?? 0))
                        .map(([priority, count]) => (
                          <div key={priority} className="flex items-center justify-between">
                            <Badge variant={priority === "urgent" ? "destructive" : priority === "high" ? "secondary" : "outline"}>
                              {priority}
                            </Badge>
                            <span className="text-sm text-muted-foreground">{count}</span>
                          </div>
                        ))}
                    </div>
                  </CardContent>
                </Card>
              </div>

              {analytics && (
                <>
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Owner Pressure</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="grid gap-3 md:grid-cols-3">
                        {analytics.owner_pressure.map((item) => (
                          <Card key={item.department_code} className="border shadow-none">
                            <CardContent className="p-4">
                              <div className="text-sm font-medium mb-2">
                                {departmentNameByCode[item.department_code] ?? item.department_code}
                              </div>
                              <div className="flex gap-3">
                                <Link href={`/issues?department_code=${item.department_code}`}>
                                  <Badge variant="secondary">{item.active_issues} active</Badge>
                                </Link>
                                <Badge variant={item.high_risk_issues > 0 ? "destructive" : "outline"}>
                                  {item.high_risk_issues} high risk
                                </Badge>
                              </div>
                            </CardContent>
                          </Card>
                        ))}
                      </div>
                    </CardContent>
                  </Card>

                  <div className="grid gap-4 md:grid-cols-2">
                    <Card>
                      <CardHeader>
                        <CardTitle className="text-base">Platform Risk</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="space-y-3">
                          {analytics.platform_risk_spread.map((item) => (
                            <div key={item.source_code} className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <PlatformLogo sourceCode={item.source_code} />
                                <span className="text-sm">{sourceNameByCode[item.source_code] ?? item.source_code}</span>
                              </div>
                              <Badge variant={item.high_risk_reviews > 0 ? "destructive" : "outline"}>
                                {item.high_risk_reviews} high risk
                              </Badge>
                            </div>
                          ))}
                        </div>
                      </CardContent>
                    </Card>

                    <Card>
                      <CardHeader>
                        <CardTitle className="text-base">Recent Issues</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="space-y-3">
                          {analytics.recent_issues.length === 0 ? (
                            <p className="text-sm text-muted-foreground">No recent issues</p>
                          ) : (
                            analytics.recent_issues.map((issue) => (
                              <div key={issue.issue_id} className="flex items-start justify-between gap-2">
                                <div>
                                  <Link href={`/issues`}>
                                    <p className="text-sm font-medium hover:underline">{issue.title}</p>
                                  </Link>
                                  <p className="text-xs text-muted-foreground">
                                    {departmentNameByCode[issue.department_code] ?? issue.department_code}
                                  </p>
                                </div>
                                <div className="flex gap-1">
                                  <Badge variant={statusBadgeVariant(issue.status)} className="text-[10px]">
                                    {issue.status}
                                  </Badge>
                                  <Badge variant={riskBadgeVariant(issue.reputation_risk_score)} className="text-[10px]">
                                    {issue.reputation_risk_score}
                                  </Badge>
                                </div>
                              </div>
                            ))
                          )}
                        </div>
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
