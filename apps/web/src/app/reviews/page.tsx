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
import type { Department, IssueCategory, Review, ReviewSource } from "@/lib/api-types"
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

function severityVariant(label: string): "default" | "secondary" | "destructive" | "outline" {
  if (label === "critical" || label === "high") return "destructive"
  if (label === "medium") return "secondary"
  return "outline"
}

function actionStatusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "ticket_created") return "default"
  if (status === "ignored") return "outline"
  return "secondary"
}

function ReviewsContent() {
  const { filters, setFilter, clearFilters, buildApiParams, hasActiveFilters } = useDashboardFilters()
  const [reviews, setReviews] = useState<Review[]>([])
  const [sources, setSources] = useState<ReviewSource[]>([])
  const [categories, setCategories] = useState<IssueCategory[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadConfig = useCallback(async () => {
    const res = await fetch(`${apiBaseUrl}/config`)
    if (!res.ok) return
    const data = await res.json()
    setSources(data.review_sources)
    setCategories(data.issue_categories)
    setDepartments(data.departments)
  }, [])

  const loadReviews = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const params = buildApiParams()
      const res = await fetch(`${apiBaseUrl}/reviews?${params}`)
      if (!res.ok) throw new Error("Failed to load reviews")
      const data = await res.json()
      setReviews(data.reviews)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load reviews")
    } finally {
      setIsLoading(false)
    }
  }, [buildApiParams])

  useEffect(() => { loadConfig() }, [loadConfig])
  useEffect(() => { loadReviews() }, [loadReviews])

  const categoryNameByCode = Object.fromEntries(categories.map((c) => [c.code, c.name]))
  const departmentNameByCode = Object.fromEntries(departments.map((d) => [d.code, d.name]))

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
                Normalized guest reviews with full filter support. Verified sources only by default.
              </p>
            </div>
            {!isLoading && (
              <Badge variant="outline">{reviews.length} {reviews.length === 1 ? "review" : "reviews"}</Badge>
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

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                {isLoading ? "Loading…" : error ? "Error" : `${reviews.length} reviews`}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {error ? (
                <p className="text-sm text-destructive">{error}</p>
              ) : isLoading ? (
                <p className="text-sm text-muted-foreground">Loading reviews…</p>
              ) : reviews.length === 0 ? (
                <p className="text-sm text-muted-foreground">No reviews match the current filters.</p>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Date</TableHead>
                        <TableHead>Source</TableHead>
                        <TableHead>Rating</TableHead>
                        <TableHead>Sentiment</TableHead>
                        <TableHead>Severity</TableHead>
                        <TableHead>Category</TableHead>
                        <TableHead>Department</TableHead>
                        <TableHead>Action status</TableHead>
                        <TableHead>Guest</TableHead>
                        <TableHead className="min-w-64">Review</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {reviews.map((review) => (
                        <TableRow key={review.id}>
                          <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                            {formatDate(review.review_date)}
                          </TableCell>
                          <TableCell className="text-xs">
                            <div className="font-medium">{review.source_name}</div>
                            {review.is_verified_channel && (
                              <Badge variant="outline" className="mt-1 text-xs">verified</Badge>
                            )}
                          </TableCell>
                          <TableCell className="text-xs">
                            {review.rating != null ? review.rating.toFixed(1) : "—"}
                          </TableCell>
                          <TableCell>
                            <Badge variant={sentimentVariant(review.sentiment_label)} className="text-xs">
                              {review.sentiment_label}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge variant={severityVariant(review.severity)} className="text-xs">
                              {review.severity}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs">
                            {categoryNameByCode[review.issue_category_code] ?? review.issue_category_code.replaceAll("_", " ")}
                          </TableCell>
                          <TableCell className="text-xs">
                            {departmentNameByCode[review.department_code] ?? review.department_code.replaceAll("_", " ")}
                          </TableCell>
                          <TableCell>
                            <Badge variant={actionStatusVariant(review.action_status)} className="text-xs">
                              {review.action_status.replaceAll("_", " ")}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs">
                            <div>{review.display_reviewer_name ?? "—"}</div>
                            {review.has_display_redactions && (
                              <Badge variant="outline" className="mt-1 text-xs">redacted</Badge>
                            )}
                          </TableCell>
                          <TableCell className="max-w-xs text-xs text-muted-foreground">
                            {review.display_title && (
                              <p className="font-medium text-foreground">{review.display_title}</p>
                            )}
                            <p className="line-clamp-2">{review.display_body}</p>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
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
