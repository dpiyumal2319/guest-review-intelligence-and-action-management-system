"use client"

import { Suspense, useCallback, useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { AppSidebar } from "@/components/app-sidebar"
import { SiteHeader } from "@/components/site-header"
import { DashboardFilterBar } from "@/components/dashboard-filter-bar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
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
import { TICKET_PRIORITIES, type Department, type IssueCategory, type Review, type ReviewSource, type ReviewsResponse, type Ticket } from "@/lib/api-types"
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

function reputationRiskVariant(label: string): "default" | "secondary" | "destructive" | "outline" {
  if (label === "critical" || label === "high") return "destructive"
  if (label === "medium") return "secondary"
  return "outline"
}

function actionStatusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "ticket_created") return "default"
  if (status === "ignored") return "outline"
  return "secondary"
}

function formatCodeLabel(value: string) {
  return value.replaceAll("_", " ")
}

function titleCaseCode(value: string) {
  return formatCodeLabel(value).replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function buildOperationalSummary(
  review: Review,
  categoryNameByCode: Record<string, string>,
  departmentNameByCode: Record<string, string>
) {
  const categoryName = categoryNameByCode[review.issue_category_code] ?? formatCodeLabel(review.issue_category_code)
  const departmentName = departmentNameByCode[review.department_code] ?? formatCodeLabel(review.department_code)

  return `Route to ${departmentName} for ${categoryName.toLowerCase()} follow-up. Reputation Risk is ${review.reputation_risk}.`
}

function ReviewTicketSheet({
  review,
  open,
  onOpenChange,
  departments,
  departmentNameByCode,
  categoryNameByCode,
  onTicketCreated,
}: {
  review: Review | null
  open: boolean
  onOpenChange: (open: boolean) => void
  departments: Department[]
  departmentNameByCode: Record<string, string>
  categoryNameByCode: Record<string, string>
  onTicketCreated: (ticket: Ticket) => void
}) {
  const [departmentCode, setDepartmentCode] = useState("")
  const [priority, setPriority] = useState("auto")
  const [assigneeName, setAssigneeName] = useState("")
  const [assigneeEmail, setAssigneeEmail] = useState("")
  const [dueDate, setDueDate] = useState("")
  const [notes, setNotes] = useState("")
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    if (!review) return
    setDepartmentCode(review.department_code)
    setPriority("auto")
    setAssigneeName("")
    setAssigneeEmail("")
    setDueDate("")
    setNotes("")
    setSaveError(null)
  }, [review])

  if (!review) return null

  const categoryName = categoryNameByCode[review.issue_category_code] ?? formatCodeLabel(review.issue_category_code)
  const departmentName = departmentNameByCode[review.department_code] ?? formatCodeLabel(review.department_code)
  const priorityLabels = {
    auto: "Auto from Reputation Risk",
    ...Object.fromEntries(TICKET_PRIORITIES.map((item) => [item, titleCaseCode(item)])),
  }

  async function submitTicket() {
    if (!review) return
    setIsSaving(true)
    setSaveError(null)
    try {
      const response = await fetch(`${apiBaseUrl}/reviews/${review.id}/tickets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          department_code: departmentCode,
          priority: priority === "auto" ? undefined : priority,
          assignee_name: assigneeName || null,
          assignee_email: assigneeEmail || null,
          due_date: dueDate ? new Date(`${dueDate}T00:00:00`).toISOString() : null,
          notes: notes || null,
        }),
      })
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({ detail: "Failed to create ticket" }))
        throw new Error(errorPayload.detail ?? "Failed to create ticket")
      }
      const created = await response.json()
      onTicketCreated(created)
      onOpenChange(false)
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "Failed to create ticket")
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader className="pb-4">
          <SheetTitle>Create ticket from review #{review.id}</SheetTitle>
          <SheetDescription>
            Convert this review into a department-owned corrective action without automatic ticket creation.
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-col gap-4 px-4 pb-4">
          <div className="rounded-lg border bg-muted/30 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={reputationRiskVariant(review.reputation_risk)} className="text-xs">
                {review.reputation_risk} risk
              </Badge>
              <Badge variant={sentimentVariant(review.sentiment_label)} className="text-xs">
                {review.sentiment_label}
              </Badge>
              <Badge variant="outline" className="text-xs">
                {categoryName}
              </Badge>
              <Badge variant="outline" className="text-xs">
                {departmentName}
              </Badge>
            </div>
            <div className="mt-3 space-y-2">
              {review.display_title && (
                <p className="text-sm font-medium text-foreground">{review.display_title}</p>
              )}
              <p className="text-xs text-muted-foreground">{review.display_reviewer_name ?? "Guest"} · {formatDate(review.review_date)}</p>
              <p className="text-sm leading-6 text-foreground">{review.display_body}</p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs">Department</Label>
              <Select value={departmentCode} onValueChange={(value) => value && setDepartmentCode(value)}>
                <SelectTrigger>
                  <SelectValue>
                    {(value) => departmentNameByCode[value] ?? value}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {departments.map((department) => (
                    <SelectItem key={department.code} value={department.code}>
                      {department.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label className="text-xs">Priority</Label>
              <Select value={priority} onValueChange={(value) => value && setPriority(value)}>
                <SelectTrigger>
                  <SelectValue>
                    {(value) => priorityLabels[value as keyof typeof priorityLabels] ?? value}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Auto from Reputation Risk</SelectItem>
                  {TICKET_PRIORITIES.map((item) => (
                    <SelectItem key={item} value={item}>
                      {item}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label className="text-xs">Assignee</Label>
              <Input value={assigneeName} onChange={(event) => setAssigneeName(event.target.value)} />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label className="text-xs">Assignee email</Label>
              <Input value={assigneeEmail} onChange={(event) => setAssigneeEmail(event.target.value)} />
            </div>

            <div className="flex flex-col gap-1.5 sm:col-span-2">
              <Label className="text-xs">Due date</Label>
              <Input type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} />
            </div>

            <div className="flex flex-col gap-1.5 sm:col-span-2">
              <Label className="text-xs">Manager note</Label>
              <textarea
                className="min-h-28 rounded-md border bg-background px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="Capture the corrective action expected from the owning department."
              />
            </div>
          </div>

          {saveError && <p className="text-sm text-destructive">{saveError}</p>}

          <div className="flex items-center justify-end gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSaving}>
              Cancel
            </Button>
            <Button onClick={submitTicket} disabled={isSaving || !departmentCode}>
              {isSaving ? "Creating..." : "Create ticket"}
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}

function ReviewsContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { filters, setFilter, clearFilters, buildApiParams, hasActiveFilters } = useDashboardFilters()
  const { activeRole, canManageTickets, scopeLabel } = useDemoRole()
  const [reviews, setReviews] = useState<Review[]>([])
  const [totalReviews, setTotalReviews] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [sources, setSources] = useState<ReviewSource[]>([])
  const [categories, setCategories] = useState<IssueCategory[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedReview, setSelectedReview] = useState<Review | null>(null)
  const [sheetOpen, setSheetOpen] = useState(false)
  const currentPage = Math.max(1, Number(searchParams.get("page") ?? "1") || 1)
  const perPage = Math.min(100, Math.max(1, Number(searchParams.get("per_page") ?? "25") || 25))

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
      const params = buildApiParams({ page: String(currentPage), per_page: String(perPage) })
      const res = await fetch(`${apiBaseUrl}/reviews?${params}`)
      if (!res.ok) throw new Error("Failed to load reviews")
      const data: ReviewsResponse = await res.json()
      setReviews(data.reviews)
      setTotalReviews(data.total)
      setTotalPages(data.total_pages)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load reviews")
    } finally {
      setIsLoading(false)
    }
  }, [buildApiParams, currentPage, perPage])

  useEffect(() => { loadConfig() }, [loadConfig])
  useEffect(() => { loadReviews() }, [loadReviews])

  const categoryNameByCode = Object.fromEntries(categories.map((c) => [c.code, c.name]))
  const departmentNameByCode = Object.fromEntries(departments.map((d) => [d.code, d.name]))

  function setPage(page: number) {
    const params = new URLSearchParams(searchParams.toString())
    if (page <= 1) {
      params.delete("page")
    } else {
      params.set("page", String(page))
    }
    router.push(`?${params.toString()}`, { scroll: false })
  }

  function openTicketSheet(review: Review) {
    setSelectedReview(review)
    setSheetOpen(true)
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
        <main className="flex flex-1 flex-col gap-4 p-4 md:p-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">Reviews</h1>
              <p className="text-sm text-muted-foreground">
                Review-platform feedback queue with operational routing and Reputation Risk context.
              </p>
              {activeRole && (
                <div className="mt-2 flex flex-wrap gap-2">
                  <Badge variant="outline" className="text-xs">
                    {activeRole.name}
                  </Badge>
                  <Badge variant="secondary" className="text-xs">
                    {scopeLabel}
                  </Badge>
                  <Badge variant={canManageTickets ? "secondary" : "outline"} className="text-xs">
                    {canManageTickets ? "Manual ticket creation enabled" : "Read-only review workflow"}
                  </Badge>
                </div>
              )}
            </div>
            {!isLoading && (
              <Badge variant="outline">{totalReviews} {totalReviews === 1 ? "review" : "reviews"}</Badge>
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
                {isLoading ? "Loading…" : error ? "Error" : `${totalReviews} reviews`}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {error ? (
                <p className="text-sm text-destructive">{error}</p>
              ) : isLoading ? (
                <p className="text-sm text-muted-foreground">Loading reviews…</p>
              ) : totalReviews === 0 ? (
                <p className="text-sm text-muted-foreground">No reviews match the current filters.</p>
              ) : (
                <div className="space-y-4">
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Date</TableHead>
                          <TableHead>Platform</TableHead>
                          <TableHead>Rating</TableHead>
                          <TableHead>Guest mood</TableHead>
                          <TableHead>Reputation Risk</TableHead>
                          <TableHead>Category</TableHead>
                          <TableHead>Department</TableHead>
                          <TableHead>Action status</TableHead>
                          <TableHead className="text-right">Action</TableHead>
                          <TableHead className="min-w-72">Review</TableHead>
                          <TableHead className="min-w-80">Operational note</TableHead>
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
                              <Badge variant={reputationRiskVariant(review.reputation_risk)} className="text-xs">
                                {review.reputation_risk}
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
                                {formatCodeLabel(review.action_status)}
                              </Badge>
                            </TableCell>
                            <TableCell className="whitespace-nowrap text-right">
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={!canManageTickets}
                                onClick={() => openTicketSheet(review)}
                              >
                                {!canManageTickets
                                  ? "Read-only role"
                                  : review.action_status === "ticket_created"
                                    ? "Create follow-up"
                                    : "Create ticket"}
                              </Button>
                            </TableCell>
                            <TableCell className="max-w-sm text-xs text-muted-foreground">
                              {review.display_title && (
                                <p className="font-medium text-foreground">{review.display_title}</p>
                              )}
                              <p className="mt-1">{review.display_reviewer_name ?? "Guest"}</p>
                              <p className="line-clamp-2">{review.display_body}</p>
                              {review.has_display_redactions && (
                                <Badge variant="outline" className="mt-2 text-xs">redacted</Badge>
                              )}
                            </TableCell>
                            <TableCell className="max-w-md text-xs text-muted-foreground">
                              {buildOperationalSummary(review, categoryNameByCode, departmentNameByCode)}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
                    <p>
                      Page {currentPage} of {totalPages || 1}, showing {reviews.length} of {totalReviews} reviews
                    </p>
                    <div className="flex items-center gap-2">
                      <Button variant="outline" size="sm" disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}>
                        Previous
                      </Button>
                      <Button variant="outline" size="sm" disabled={totalPages === 0 || currentPage >= totalPages} onClick={() => setPage(currentPage + 1)}>
                        Next
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </main>
      </SidebarInset>

      <ReviewTicketSheet
        review={selectedReview}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        departments={departments}
        departmentNameByCode={departmentNameByCode}
        categoryNameByCode={categoryNameByCode}
        onTicketCreated={() => {
          void loadReviews()
        }}
      />
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
