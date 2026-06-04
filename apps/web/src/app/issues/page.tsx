"use client"

import { Suspense, useCallback, useEffect, useState } from "react"
import { AppSidebar } from "@/components/app-sidebar"
import { SiteHeader } from "@/components/site-header"
import { DashboardFilterBar } from "@/components/dashboard-filter-bar"
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
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { useDashboardFilters } from "@/hooks/use-dashboard-filters"
import { useDemoRole } from "@/hooks/use-demo-role"
import type {
  Department,
  IssueCategory,
  IssueSummary,
  IssueSummaryItem,
  ReviewSource,
} from "@/lib/api-types"
import type React from "react"

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

function reputationRiskScoreVariant(score: number): "default" | "secondary" | "destructive" | "outline" {
  if (score >= 75) return "destructive"
  if (score >= 50) return "secondary"
  return "outline"
}

function reputationRiskLabelVariant(label: string): "default" | "secondary" | "destructive" | "outline" {
  if (label === "critical" || label === "high") return "destructive"
  if (label === "medium") return "secondary"
  return "outline"
}

function formatDate(value: string | null) {
  if (!value) return "—"
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value))
}

function CategorySummaryTable({
  items,
  categoryNameByCode,
  departmentNameByCode,
  sourceNameByCode,
  onCreateTicket,
  creatingTicketFor,
  canManageTickets,
}: {
  items: IssueSummaryItem[]
  categoryNameByCode: Record<string, string>
  departmentNameByCode: Record<string, string>
  sourceNameByCode: Record<string, string>
  onCreateTicket: (item: IssueSummaryItem) => void
  creatingTicketFor: string | null
  canManageTickets: boolean
}) {
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">No recurring issue groups match the current filters.</p>
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Issue group</TableHead>
            <TableHead className="text-right">Recent count</TableHead>
            <TableHead className="text-right">Total reviews</TableHead>
            <TableHead className="text-right">Avg Reputation Risk</TableHead>
            <TableHead>Highest risk</TableHead>
            <TableHead>Platform mix</TableHead>
            <TableHead>Last review</TableHead>
            <TableHead>Tickets</TableHead>
            <TableHead className="text-right">Action</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.group_key}>
              <TableCell className="min-w-64">
                <div className="font-medium text-sm">
                  {categoryNameByCode[item.category_code] ?? item.category_name}
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {departmentNameByCode[item.department_code] ?? item.department_code.replaceAll("_", " ")}
                </div>
              </TableCell>
              <TableCell className="text-right text-sm">{item.recent_review_count}</TableCell>
              <TableCell className="text-right text-sm">{item.review_count}</TableCell>
              <TableCell className="text-right">
                <Badge variant={reputationRiskScoreVariant(item.average_reputation_risk_score)} className="text-xs tabular-nums">
                  {item.average_reputation_risk_score.toFixed(1)}
                </Badge>
              </TableCell>
              <TableCell>
                <Badge variant={reputationRiskLabelVariant(item.highest_reputation_risk)} className="text-xs">
                  {item.highest_reputation_risk}
                </Badge>
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {Object.entries(item.source_mix)
                  .sort(([, a], [, b]) => b - a)
                  .map(([src, count]) => `${sourceNameByCode[src] ?? src}: ${count}`)
                  .join(", ")}
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {formatDate(item.latest_review_date)}
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {item.linked_ticket_ids.length > 0
                  ? item.linked_ticket_ids.map((id) => `#${id}`).join(", ")
                  : "—"}
              </TableCell>
              <TableCell className="text-right">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!canManageTickets || creatingTicketFor === item.group_key}
                  onClick={() => onCreateTicket(item)}
                >
                  {!canManageTickets ? "Read-only role" : creatingTicketFor === item.group_key ? "Creating…" : "Create ticket"}
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function IssuesContent() {
  const { filters, setFilter, clearFilters, buildApiParams, hasActiveFilters } = useDashboardFilters()
  const { activeRole, canManageTickets, departments: scopedDepartments, effectiveDepartmentCode, scopeLabel } = useDemoRole()
  const [issueSummary, setIssueSummary] = useState<IssueSummary | null>(null)
  const [sources, setSources] = useState<ReviewSource[]>([])
  const [categories, setCategories] = useState<IssueCategory[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [isLoadingSummary, setIsLoadingSummary] = useState(true)
  const [summaryError, setSummaryError] = useState<string | null>(null)
  const [creatingGroupTicket, setCreatingGroupTicket] = useState<string | null>(null)

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
      if (!params.get("department_code") && effectiveDepartmentCode) {
        params.set("department_code", effectiveDepartmentCode)
      }
      const res = await fetch(`${apiBaseUrl}/issues/summary?${params}`)
      if (!res.ok) throw new Error("Failed to load issue summary")
      const data = await res.json()
      setIssueSummary(data)
    } catch (err) {
      setSummaryError(err instanceof Error ? err.message : "Failed to load issue summary")
    } finally {
      setIsLoadingSummary(false)
    }
  }, [buildApiParams, effectiveDepartmentCode])

  useEffect(() => { loadConfig() }, [loadConfig])
  useEffect(() => { loadIssueSummary() }, [loadIssueSummary])

  const categoryNameByCode = Object.fromEntries(categories.map((c) => [c.code, c.name]))
  const departmentNameByCode = Object.fromEntries(departments.map((d) => [d.code, d.name]))
  const sourceNameByCode = Object.fromEntries(sources.map((s) => [s.code, s.name]))
  const scopedDepartmentName = scopedDepartments.find((department) => department.code === effectiveDepartmentCode)?.name
  const topGroups = issueSummary?.items.slice(0, 3) ?? []

  async function createGroupTicket(item: IssueSummaryItem) {
    if (!canManageTickets) return
    setCreatingGroupTicket(item.group_key)
    setSummaryError(null)
    try {
      const params = buildApiParams()
      if (!params.get("department_code") && effectiveDepartmentCode) {
        params.set("department_code", effectiveDepartmentCode)
      }
      const res = await fetch(`${apiBaseUrl}/issues/groups/${item.category_code}/${item.department_code}/tickets?${params}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          department_code: item.department_code,
          priority: item.highest_reputation_risk === "critical" ? "urgent" : item.highest_reputation_risk === "high" ? "high" : "medium",
          notes: `Created from ${item.recent_review_count} recent reviews in the ${item.category_name} / ${departmentNameByCode[item.department_code] ?? item.department_code} issue group.`,
        }),
      })
      if (!res.ok) throw new Error("Failed to create ticket from recurring issue group")
      await loadIssueSummary()
    } catch (err) {
      setSummaryError(err instanceof Error ? err.message : "Failed to create ticket from recurring issue group")
    } finally {
      setCreatingGroupTicket(null)
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
        <main className="flex flex-1 flex-col gap-4 p-4 md:p-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">Issues</h1>
              <p className="text-sm text-muted-foreground">
                Recurring operational issues grouped by category and department, using recent review-platform feedback.
              </p>
              {activeRole && (
                <div className="mt-2 flex flex-wrap gap-2">
                  <Badge variant="outline" className="text-xs">{activeRole.name}</Badge>
                  <Badge variant="secondary" className="text-xs">{scopeLabel}</Badge>
                  <Badge variant={canManageTickets ? "secondary" : "outline"} className="text-xs">
                    {canManageTickets ? "Can create tickets" : "Read-only ticket workflow"}
                  </Badge>
                  {effectiveDepartmentCode && !filters.department_code && scopedDepartmentName && (
                    <Badge variant="outline" className="text-xs">
                      Defaulting to {scopedDepartmentName}
                    </Badge>
                  )}
                </div>
              )}
            </div>
            {!isLoadingSummary && issueSummary && (
              <Badge variant="outline">
                {issueSummary.items.length} {issueSummary.items.length === 1 ? "issue group" : "issue groups"}
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

          <section className="grid gap-4 md:grid-cols-3">
            {topGroups.map((item) => (
              <Card key={item.group_key}>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">
                    {categoryNameByCode[item.category_code] ?? item.category_name}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm text-muted-foreground">
                  <p>{departmentNameByCode[item.department_code] ?? item.department_code.replaceAll("_", " ")}</p>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="outline">{item.recent_review_count} recent</Badge>
                    <Badge variant="outline">{item.review_count} total</Badge>
                    <Badge variant={reputationRiskLabelVariant(item.highest_reputation_risk)}>
                      {item.highest_reputation_risk} risk
                    </Badge>
                  </div>
                  <p>
                    Platform mix: {Object.entries(item.source_mix).map(([src, count]) => `${sourceNameByCode[src] ?? src}: ${count}`).join(", ")}
                  </p>
                </CardContent>
              </Card>
            ))}
          </section>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                {isLoadingSummary
                  ? "Loading…"
                  : summaryError
                    ? "Error"
                    : `${issueSummary?.items.length ?? 0} recurring ${issueSummary?.items.length === 1 ? "issue group" : "issue groups"}`}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {summaryError ? (
                <p className="text-sm text-destructive">{summaryError}</p>
              ) : isLoadingSummary ? (
                <p className="text-sm text-muted-foreground">Loading recurring issue groups…</p>
              ) : (
                <CategorySummaryTable
                  items={issueSummary?.items ?? []}
                  categoryNameByCode={categoryNameByCode}
                  departmentNameByCode={departmentNameByCode}
                  sourceNameByCode={sourceNameByCode}
                  onCreateTicket={createGroupTicket}
                  creatingTicketFor={creatingGroupTicket}
                  canManageTickets={canManageTickets}
                />
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
