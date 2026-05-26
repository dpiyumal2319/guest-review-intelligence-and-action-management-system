"use client"

import { Suspense, useCallback, useEffect, useState } from "react"
import { AppSidebar } from "@/components/app-sidebar"
import { SiteHeader } from "@/components/site-header"
import { DashboardFilterBar } from "@/components/dashboard-filter-bar"
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
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { useDashboardFilters } from "@/hooks/use-dashboard-filters"
import type {
  Department,
  IssueCategory,
  IssueSummary,
  IssueSummaryItem,
  ReviewSource,
  SemanticAnalysis,
  SemanticIssueCluster,
} from "@/lib/api-types"
import type React from "react"

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

function severityScoreVariant(score: number): "default" | "secondary" | "destructive" | "outline" {
  if (score >= 75) return "destructive"
  if (score >= 50) return "secondary"
  return "outline"
}

function CategorySummaryTable({
  items,
  categoryNameByCode,
  departmentNameByCode,
  sourceNameByCode,
}: {
  items: IssueSummaryItem[]
  categoryNameByCode: Record<string, string>
  departmentNameByCode: Record<string, string>
  sourceNameByCode: Record<string, string>
}) {
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">No issues match the current filters.</p>
  }
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Category</TableHead>
            <TableHead className="text-right">Reviews</TableHead>
            <TableHead className="text-right">Avg severity score</TableHead>
            <TableHead>Primary department</TableHead>
            <TableHead>Source mix</TableHead>
            <TableHead className="text-right">Rep. review ID</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.category_code}>
              <TableCell className="font-medium text-sm">
                {categoryNameByCode[item.category_code] ?? item.category_code.replaceAll("_", " ")}
              </TableCell>
              <TableCell className="text-right text-sm">{item.review_count}</TableCell>
              <TableCell className="text-right">
                <Badge variant={severityScoreVariant(item.average_severity_score)} className="text-xs tabular-nums">
                  {item.average_severity_score.toFixed(1)}
                </Badge>
              </TableCell>
              <TableCell className="text-xs">
                {departmentNameByCode[item.primary_department_code] ?? item.primary_department_code.replaceAll("_", " ")}
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {Object.entries(item.source_mix)
                  .sort(([, a], [, b]) => b - a)
                  .map(([src, count]) => `${sourceNameByCode[src] ?? src}: ${count}`)
                  .join(", ")}
              </TableCell>
              <TableCell className="text-right text-xs text-muted-foreground tabular-nums">
                #{item.representative_review_id}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function SemanticClusterCard({ cluster, categoryNameByCode, departmentNameByCode }: {
  cluster: SemanticIssueCluster
  categoryNameByCode: Record<string, string>
  departmentNameByCode: Record<string, string>
}) {
  return (
    <div className="rounded-lg border bg-card p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant="outline" className="text-xs">
            {categoryNameByCode[cluster.category_code] ?? cluster.category_code.replaceAll("_", " ")}
          </Badge>
          <Badge variant="secondary" className="text-xs">
            {departmentNameByCode[cluster.department_code] ?? cluster.department_code.replaceAll("_", " ")}
          </Badge>
          <span className="text-xs text-muted-foreground">{cluster.size} reviews</span>
          <span className="text-xs text-muted-foreground">
            avg similarity {(cluster.average_similarity * 100).toFixed(0)}%
          </span>
        </div>
        <span className="text-xs text-muted-foreground whitespace-nowrap">cluster {cluster.cluster_id}</span>
      </div>
      <p className="text-sm line-clamp-3 text-muted-foreground">{cluster.representative_text}</p>
      <div className="flex flex-wrap gap-1">
        {cluster.review_ids.map((id) => (
          <span key={id} className="inline-flex items-center rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
            #{id}
          </span>
        ))}
      </div>
    </div>
  )
}

function IssuesContent() {
  const { filters, setFilter, clearFilters, buildApiParams, hasActiveFilters } = useDashboardFilters()
  const [issueSummary, setIssueSummary] = useState<IssueSummary | null>(null)
  const [semanticAnalysis, setSemanticAnalysis] = useState<SemanticAnalysis | null>(null)
  const [sources, setSources] = useState<ReviewSource[]>([])
  const [categories, setCategories] = useState<IssueCategory[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [isLoadingSummary, setIsLoadingSummary] = useState(true)
  const [isLoadingClusters, setIsLoadingClusters] = useState(true)
  const [summaryError, setSummaryError] = useState<string | null>(null)
  const [clustersError, setClustersError] = useState<string | null>(null)

  const loadConfig = useCallback(async () => {
    const res = await fetch(`${apiBaseUrl}/config`)
    if (!res.ok) return
    const data = await res.json()
    setSources(data.review_sources)
    setCategories(data.issue_categories)
    setDepartments(data.departments)
  }, [])

  const loadIssueSummary = useCallback(async () => {
    setIsLoadingSummary(true)
    setSummaryError(null)
    try {
      const params = buildApiParams()
      const res = await fetch(`${apiBaseUrl}/issues/summary?${params}`)
      if (!res.ok) throw new Error("Failed to load issue summary")
      const data = await res.json()
      setIssueSummary(data)
    } catch (err) {
      setSummaryError(err instanceof Error ? err.message : "Failed to load issue summary")
    } finally {
      setIsLoadingSummary(false)
    }
  }, [buildApiParams])

  const loadSemanticClusters = useCallback(async () => {
    setIsLoadingClusters(true)
    setClustersError(null)
    try {
      const params = buildApiParams()
      const res = await fetch(`${apiBaseUrl}/analysis/semantic-clusters?${params}`)
      if (!res.ok) throw new Error("Failed to load semantic clusters")
      const data = await res.json()
      setSemanticAnalysis(data)
    } catch (err) {
      setClustersError(err instanceof Error ? err.message : "Failed to load semantic clusters")
    } finally {
      setIsLoadingClusters(false)
    }
  }, [buildApiParams])

  useEffect(() => { loadConfig() }, [loadConfig])
  useEffect(() => { loadIssueSummary() }, [loadIssueSummary])
  useEffect(() => { loadSemanticClusters() }, [loadSemanticClusters])

  const categoryNameByCode = Object.fromEntries(categories.map((c) => [c.code, c.name]))
  const departmentNameByCode = Object.fromEntries(departments.map((d) => [d.code, d.name]))
  const sourceNameByCode = Object.fromEntries(sources.map((s) => [s.code, s.name]))

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
              <h1 className="text-2xl font-semibold tracking-tight">Issues</h1>
              <p className="text-sm text-muted-foreground">
                Category aggregates and semantic clusters. Verified sources only by default.
              </p>
            </div>
            {!isLoadingSummary && issueSummary && (
              <Badge variant="outline">
                {issueSummary.total_reviews} {issueSummary.total_reviews === 1 ? "review" : "reviews"}
              </Badge>
            )}
          </div>

          <DashboardFilterBar
            filters={filters}
            onFilterChange={setFilter}
            onClear={clearFilters}
            hasActiveFilters={hasActiveFilters}
            sources={sources}
            categories={categories}
            departments={departments}
          />

          {/* Category summary */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                {isLoadingSummary
                  ? "Loading…"
                  : summaryError
                  ? "Error"
                  : `${issueSummary?.items.length ?? 0} ${issueSummary?.items.length === 1 ? "category" : "categories"}`}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {summaryError ? (
                <p className="text-sm text-destructive">{summaryError}</p>
              ) : isLoadingSummary ? (
                <p className="text-sm text-muted-foreground">Loading category summary…</p>
              ) : (
                <CategorySummaryTable
                  items={issueSummary?.items ?? []}
                  categoryNameByCode={categoryNameByCode}
                  departmentNameByCode={departmentNameByCode}
                  sourceNameByCode={sourceNameByCode}
                />
              )}
            </CardContent>
          </Card>

          {/* Semantic clusters */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                {isLoadingClusters
                  ? "Loading…"
                  : clustersError
                  ? "Error"
                  : `${semanticAnalysis?.clusters.length ?? 0} semantic ${semanticAnalysis?.clusters.length === 1 ? "cluster" : "clusters"}`}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {clustersError ? (
                <p className="text-sm text-destructive">{clustersError}</p>
              ) : isLoadingClusters ? (
                <p className="text-sm text-muted-foreground">Loading semantic clusters…</p>
              ) : !semanticAnalysis || semanticAnalysis.clusters.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No clusters found with the current filters and minimum cluster size.
                </p>
              ) : (
                <div className="flex flex-col gap-3">
                  {semanticAnalysis.clusters.map((cluster) => (
                    <SemanticClusterCard
                      key={cluster.cluster_id}
                      cluster={cluster}
                      categoryNameByCode={categoryNameByCode}
                      departmentNameByCode={departmentNameByCode}
                    />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

export default function IssuesPage() {
  return (
    <Suspense>
      <IssuesContent />
    </Suspense>
  )
}
