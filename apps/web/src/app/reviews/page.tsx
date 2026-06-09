"use client"

import { Suspense, useCallback, useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { AppSidebar } from "@/components/app-sidebar"
import { SiteHeader } from "@/components/site-header"
import { DashboardFilterBar } from "@/components/dashboard-filter-bar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
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
import { useDemoRole } from "@/hooks/use-demo-role"
import { getPlatformMeta } from "@/lib/platform-meta"
import type { Department, ReviewSource, ReviewsResponse } from "@/lib/api-types"
import type React from "react"

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

function formatDate(value: string | null) {
  if (!value) return "—"
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value))
}

function sentimentVariant(label: string): "default" | "secondary" | "destructive" | "outline" {
  if (label === "positive") return "default"
  if (label === "negative") return "destructive"
  return "secondary"
}

function riskLabelVariant(label: string): "default" | "secondary" | "destructive" | "outline" {
  if (label === "critical" || label === "high") return "destructive"
  if (label === "medium") return "secondary"
  return "outline"
}

function ReviewsContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { filters, setFilter, clearFilters, buildApiParams, hasActiveFilters } = useDashboardFilters()
  const { activeRole, scopeLabel } = useDemoRole()
  const [data, setData] = useState<ReviewsResponse | null>(null)
  const [sources, setSources] = useState<ReviewSource[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedReview, setExpandedReview] = useState<number | null>(null)

  const page = parseInt(searchParams.get("page") ?? "1", 10)
  const orderBy = searchParams.get("order_by") ?? "review_date"

  const loadConfig = useCallback(async () => {
    const res = await fetch(`${apiBaseUrl}/config`)
    if (!res.ok) return
    const data = await res.json()
    setSources(data.review_sources)
    setDepartments(data.departments)
  }, [])

  const loadReviews = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = buildApiParams({ page: String(page), per_page: "25", order_by: orderBy })
      const res = await fetch(`${apiBaseUrl}/reviews?${params}`)
      if (!res.ok) throw new Error("Failed to load reviews")
      setData(await res.json())
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load reviews")
    } finally {
      setLoading(false)
    }
  }, [buildApiParams, page, orderBy])

  useEffect(() => { loadConfig() }, [loadConfig])
  useEffect(() => { loadReviews() }, [loadReviews])

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
              <h1 className="text-2xl font-semibold tracking-tight">Reviews</h1>
              <p className="text-sm text-muted-foreground">
                Guest reviews imported from connected review platforms.
              </p>
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
            showSearch
            showRiskGroup
            showHasIssues
          />

          <Card>
            <CardContent className="p-0">
              {loading ? (
                <p className="p-4 text-sm text-muted-foreground">Loading reviews...</p>
              ) : error ? (
                <p className="p-4 text-sm text-destructive">{error}</p>
              ) : !data || data.reviews.length === 0 ? (
                <p className="p-4 text-sm text-muted-foreground">No reviews found.</p>
              ) : (
                <>
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Date</TableHead>
                          <TableHead>Platform</TableHead>
                          <TableHead>Rating</TableHead>
                          <TableHead>Sentiment</TableHead>
                          <TableHead>Risk</TableHead>
                          <TableHead>Department</TableHead>
                          <TableHead>Issues</TableHead>
                          <TableHead>Review</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {data.reviews.map((review) => (
                          <TableRow
                            key={review.id}
                            className="cursor-pointer hover:bg-muted/50"
                            onClick={() => setExpandedReview(expandedReview === review.id ? null : review.id)}
                          >
                            <TableCell className="text-xs whitespace-nowrap">
                              {formatDate(review.review_date)}
                            </TableCell>
                            <TableCell className="text-xs">
                              {(() => {
                                const meta = getPlatformMeta(review.source_code)
                                const name = sourceNameByCode[review.source_code] ?? review.source_code
                                return (
                                  <span className="flex items-center gap-1.5">
                                    {meta?.logo && (
                                      <img src={meta.logo} alt="" className="size-3.5 shrink-0 object-contain" />
                                    )}
                                    {name}
                                  </span>
                                )
                              })()}
                            </TableCell>
                            <TableCell className="text-xs">{review.rating ?? "—"}</TableCell>
                            <TableCell>
                              {review.analysis ? (
                                <Badge variant={sentimentVariant(review.analysis.sentiment_label)} className="text-xs">
                                  {review.analysis.sentiment_label}
                                </Badge>
                              ) : (
                                <span className="text-xs text-muted-foreground">{"—"}</span>
                              )}
                            </TableCell>
                            <TableCell>
                              {review.analysis ? (
                                <Badge variant={riskLabelVariant(review.analysis.reputation_risk_label)} className="text-xs">
                                  {review.analysis.reputation_risk_label} ({review.analysis.reputation_risk_score})
                                </Badge>
                              ) : (
                                <span className="text-xs text-muted-foreground">{"—"}</span>
                              )}
                            </TableCell>
                            <TableCell className="text-xs">
                              {review.analysis
                                ? (departmentNameByCode[review.analysis.department_code] ?? review.analysis.department_code)
                                : "—"}
                            </TableCell>
                            <TableCell>
                              <div className="flex flex-wrap gap-1">
                                {review.issue_links.map((link) => (
                                  <Badge key={link.id} variant="secondary" className="text-[10px]">
                                    {link.is_triggering_evidence ? "" : ""}#{link.issue_id}
                                  </Badge>
                                ))}
                                {review.issue_links.length === 0 && (
                                  <span className="text-xs text-muted-foreground">{"—"}</span>
                                )}
                              </div>
                            </TableCell>
                            <TableCell className="max-w-64">
                              <p className="text-xs font-medium truncate">
                                {review.display_title || "—"}
                              </p>
                              <p className="text-xs text-muted-foreground line-clamp-1">
                                {review.display_body}
                              </p>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>

                  {data.total_pages > 1 && (
                    <div className="flex items-center justify-between p-4">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={page <= 1}
                        onClick={() => router.push(`?${new URLSearchParams({ ...Object.fromEntries(searchParams), page: String(page - 1) }).toString()}`)}
                      >
                        Previous
                      </Button>
                      <span className="text-xs text-muted-foreground">
                        Page {data.page} of {data.total_pages} ({data.total} reviews)
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={page >= data.total_pages}
                        onClick={() => router.push(`?${new URLSearchParams({ ...Object.fromEntries(searchParams), page: String(page + 1) }).toString()}`)}
                      >
                        Next
                      </Button>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

export default function ReviewsPage() {
  return (
    <Suspense>
      <ReviewsContent />
    </Suspense>
  )
}
