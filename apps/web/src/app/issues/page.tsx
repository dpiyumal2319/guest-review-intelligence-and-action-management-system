"use client"

import { Suspense, useCallback, useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { AppSidebar } from "@/components/app-sidebar"
import { SiteHeader } from "@/components/site-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useDemoRole } from "@/hooks/use-demo-role"
import type {
  Department,
  DetectedIssue,
  IssueEmerging,
  IssuesResponse,
} from "@/lib/api-types"
import type React from "react"

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

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

function formatDate(value: string | null) {
  if (!value) return "\u2014"
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value))
}

function IssueDetailSheet({
  issue,
  departmentNameByCode,
  onClose,
  onResolve,
}: {
  issue: DetectedIssue
  departmentNameByCode: Record<string, string>
  onClose: () => void
  onResolve: (id: number) => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-end">
      <div className="fixed inset-0 bg-black/40" onClick={onClose} />
      <div className="relative z-50 h-full w-full max-w-lg overflow-auto border-l bg-background p-6 shadow-xl">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold">{issue.title}</h2>
            <p className="text-sm text-muted-foreground">
              {departmentNameByCode[issue.department_code] ?? issue.department_code}
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
        </div>

        {issue.description && (
          <p className="text-sm mb-4 leading-relaxed">{issue.description}</p>
        )}

        <div className="flex flex-wrap gap-2 mb-4">
          <Badge variant={statusBadgeVariant(issue.status)}>{issue.status}</Badge>
          <Badge variant={riskBadgeVariant(issue.reputation_risk_score)}>
            Risk: {issue.reputation_risk_score}
          </Badge>
          <Badge variant="outline">Priority: {issue.priority}</Badge>
          <Badge variant="outline">Recurrence: {issue.recurrence_count}x</Badge>
        </div>

        {issue.keywords && issue.keywords.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-4">
            {issue.keywords.map((kw) => (
              <Badge key={kw} variant="secondary" className="text-xs font-normal">
                {kw}
              </Badge>
            ))}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3 mb-4 text-sm">
          <div>
            <span className="text-muted-foreground">First seen:</span>{" "}
            {formatDate(issue.first_seen_at)}
          </div>
          <div>
            <span className="text-muted-foreground">Last seen:</span>{" "}
            {formatDate(issue.last_seen_at)}
          </div>
          <div>
            <span className="text-muted-foreground">Resolved:</span>{" "}
            {issue.resolved_at ? formatDate(issue.resolved_at) : "\u2014"}
          </div>
          <div>
            <span className="text-muted-foreground">Recurred:</span>{" "}
            {issue.recurred_at ? formatDate(issue.recurred_at) : "\u2014"}
          </div>
          <div>
            <span className="text-muted-foreground">Assignee:</span>{" "}
            {issue.assignee_name ?? "\u2014"}
          </div>
          <div>
            <span className="text-muted-foreground">Title by:</span>{" "}
            {issue.title_generated_by}
          </div>
        </div>

        {(issue.status === "active" || issue.status === "recurred") && (
          <div className="mb-4">
            <Button
              size="sm"
              onClick={() => onResolve(issue.id)}
            >
              Mark Resolved
            </Button>
          </div>
        )}

        {issue.review_links.length > 0 && (
          <div className="mb-4">
            <h3 className="text-sm font-semibold mb-2">Linked Reviews ({issue.review_links.length})</h3>
            <div className="space-y-2 max-h-64 overflow-auto">
              {issue.review_links.map((link) => (
                <div key={link.id} className="rounded border p-2 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">Review #{link.review_id}</span>
                    <span className="text-muted-foreground">
                      Similarity: {(link.similarity_score * 100).toFixed(0)}%
                    </span>
                    {link.is_triggering_evidence && (
                      <Badge variant="secondary" className="text-[10px]">Trigger</Badge>
                    )}
                  </div>
                  {link.evidence_snippet && (
                    <p className="mt-1 text-muted-foreground line-clamp-2">
                      {link.evidence_snippet}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {issue.events.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold mb-2">Event History</h3>
            <div className="space-y-2 max-h-48 overflow-auto">
              {issue.events.map((event) => (
                <div key={event.id} className="flex items-start gap-2 text-xs">
                  <span className="text-muted-foreground w-24 shrink-0">
                    {formatDate(event.created_at)}
                  </span>
                  <div>
                    <span className="font-medium">{event.event_type}</span>
                    {event.note && (
                      <p className="text-muted-foreground">{event.note}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function IssuesContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { activeRole, scopeLabel } = useDemoRole()
  const [departments, setDepartments] = useState<Department[]>([])
  const [activeIssues, setActiveIssues] = useState<IssuesResponse | null>(null)
  const [emergingIssues, setEmergingIssues] = useState<IssueEmerging[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedIssue, setSelectedIssue] = useState<DetectedIssue | null>(null)
  const [activeTab, setActiveTab] = useState("active")

  const page = parseInt(searchParams.get("page") ?? "1", 10)
  const perPage = 25

  const filterStatus = searchParams.get("status") ?? ""
  const filterDepartment = searchParams.get("department") ?? ""
  const filterPriority = searchParams.get("priority") ?? ""
  const filterMinRisk = searchParams.get("min_risk") ?? ""

  function pushFilter(key: string, value: string) {
    const params = new URLSearchParams(searchParams.toString())
    if (value) {
      params.set(key, value)
    } else {
      params.delete(key)
    }
    params.set("page", "1")
    router.push(`?${params.toString()}`)
  }

  function clearFilters() {
    router.push("?")
  }

  const hasActiveFilters = filterStatus || filterDepartment || filterPriority || filterMinRisk

  const loadConfig = useCallback(async () => {
    const res = await fetch(`${apiBaseUrl}/config`)
    if (!res.ok) return
    const data = await res.json()
    setDepartments(data.departments)
  }, [])

  const loadData = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const qs = new URLSearchParams({ page: String(page), per_page: String(perPage) })
      if (filterStatus) qs.set("status", filterStatus)
      if (filterDepartment) qs.set("department_code", filterDepartment)
      if (filterPriority) qs.set("priority", filterPriority)
      if (filterMinRisk) qs.set("min_risk", filterMinRisk)

      const [issuesRes, emergingRes] = await Promise.all([
        fetch(`${apiBaseUrl}/issues?${qs.toString()}`),
        fetch(`${apiBaseUrl}/issues/emerging`),
      ])
      if (!issuesRes.ok) throw new Error("Failed to load issues")
      const issuesData = await issuesRes.json()
      setActiveIssues(issuesData)

      if (emergingRes.ok) {
        const emergingData = await emergingRes.json()
        setEmergingIssues(emergingData)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load")
    } finally {
      setIsLoading(false)
    }
  }, [page, filterStatus, filterDepartment, filterPriority, filterMinRisk])

  useEffect(() => { loadConfig() }, [loadConfig])
  useEffect(() => { loadData() }, [loadData])

  const departmentNameByCode = Object.fromEntries(departments.map((d) => [d.code, d.name]))

  async function loadIssueDetail(issueId: number) {
    const res = await fetch(`${apiBaseUrl}/issues/${issueId}`)
    if (!res.ok) return
    const data = await res.json()
    setSelectedIssue(data)
  }

  async function resolveIssue(issueId: number) {
    const res = await fetch(`${apiBaseUrl}/issues/${issueId}/resolve`, { method: "PATCH" })
    if (!res.ok) return
    setSelectedIssue(null)
    loadData()
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
                Operational issues discovered from guest review content.
              </p>
              {activeRole && (
                <div className="mt-2 flex flex-wrap gap-2">
                  <Badge variant="outline" className="text-xs">{activeRole.name}</Badge>
                  <Badge variant="secondary" className="text-xs">{scopeLabel}</Badge>
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Select value={filterStatus || "all"} onValueChange={(v) => pushFilter("status", !v || v === "all" ? "" : v)}>
              <SelectTrigger className="h-8 w-36 text-xs">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="recurred">Recurred</SelectItem>
                <SelectItem value="resolved">Resolved</SelectItem>
              </SelectContent>
            </Select>

            <Select value={filterDepartment || "all"} onValueChange={(v) => pushFilter("department", !v || v === "all" ? "" : v)}>
              <SelectTrigger className="h-8 w-40 text-xs">
                <SelectValue placeholder="Department" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All departments</SelectItem>
                {departments.map((d) => (
                  <SelectItem key={d.code} value={d.code}>{d.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={filterPriority || "all"} onValueChange={(v) => pushFilter("priority", !v || v === "all" ? "" : v)}>
              <SelectTrigger className="h-8 w-36 text-xs">
                <SelectValue placeholder="Priority" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All priorities</SelectItem>
                <SelectItem value="urgent">Urgent</SelectItem>
                <SelectItem value="high">High</SelectItem>
                <SelectItem value="medium">Medium</SelectItem>
                <SelectItem value="low">Low</SelectItem>
              </SelectContent>
            </Select>

            <div className="relative">
              <Input
                type="number"
                min={0}
                max={100}
                placeholder="Min risk score"
                value={filterMinRisk}
                onChange={(e) => pushFilter("min_risk", e.target.value)}
                className="h-8 w-36 text-xs"
              />
            </div>

            {hasActiveFilters && (
              <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={clearFilters}>
                Clear filters
              </Button>
            )}
          </div>

          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList>
                <TabsTrigger value="active">
                  Active Issues
                  {activeIssues && (
                    <Badge variant="secondary" className="ml-2 text-xs">
                      {activeIssues.total}
                    </Badge>
                  )}
                </TabsTrigger>
              <TabsTrigger value="emerging">
                Emerging
                {emergingIssues.length > 0 && (
                  <Badge variant="outline" className="ml-2 text-xs">
                    {emergingIssues.length}
                  </Badge>
                )}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="active" className="space-y-4">
              {isLoading ? (
                <p className="text-sm text-muted-foreground">Loading issues...</p>
              ) : error ? (
                <p className="text-sm text-destructive">{error}</p>
              ) : !activeIssues || activeIssues.issues.length === 0 ? (
                <Card>
                  <CardContent className="py-8 text-center text-sm text-muted-foreground">
                    No issues detected yet. Import reviews and run issue detection.
                  </CardContent>
                </Card>
              ) : (
                <Card>
                  <CardContent className="p-0">
                    <div className="overflow-x-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Issue</TableHead>
                            <TableHead>Department</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead>Priority</TableHead>
                            <TableHead className="text-right">Risk</TableHead>
                            <TableHead className="text-right">Recurrence</TableHead>
                            <TableHead>Last seen</TableHead>
                            <TableHead>Assignee</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {activeIssues.issues.map((issue) => (
                            <TableRow
                              key={issue.id}
                              className="cursor-pointer hover:bg-muted/50"
                              onClick={() => loadIssueDetail(issue.id)}
                            >
                              <TableCell className="text-sm max-w-72">
                                <div className="font-medium truncate">{issue.title}</div>
                                {issue.description && (
                                  <div className="text-xs text-muted-foreground line-clamp-2">
                                    {issue.description}
                                  </div>
                                )}
                              </TableCell>
                              <TableCell className="text-sm">
                                {departmentNameByCode[issue.department_code] ?? issue.department_code}
                              </TableCell>
                              <TableCell>
                                <Badge variant={statusBadgeVariant(issue.status)} className="text-xs">
                                  {issue.status}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                <Badge variant="outline" className="text-xs">{issue.priority}</Badge>
                              </TableCell>
                              <TableCell className="text-right">
                                <Badge variant={riskBadgeVariant(issue.reputation_risk_score)} className="text-xs tabular-nums">
                                  {issue.reputation_risk_score}
                                </Badge>
                              </TableCell>
                              <TableCell className="text-right text-sm">{issue.recurrence_count}</TableCell>
                              <TableCell className="text-xs text-muted-foreground">
                                {formatDate(issue.last_seen_at)}
                              </TableCell>
                              <TableCell className="text-sm text-muted-foreground">
                                {issue.assignee_name ?? "\u2014"}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>

                  {activeIssues.total_pages > 1 && (
                    <div className="flex items-center justify-between p-4">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={page <= 1}
                        onClick={() => {
                          const params = new URLSearchParams(searchParams.toString())
                          params.set("page", String(page - 1))
                          router.push(`?${params.toString()}`)
                        }}
                      >
                        Previous
                      </Button>
                      <span className="text-xs text-muted-foreground">
                        Page {activeIssues.page} of {activeIssues.total_pages} ({activeIssues.total} issues)
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={page >= activeIssues.total_pages}
                        onClick={() => {
                          const params = new URLSearchParams(searchParams.toString())
                          params.set("page", String(page + 1))
                          router.push(`?${params.toString()}`)
                        }}
                      >
                        Next
                      </Button>
                    </div>
                  )}
                  </CardContent>
                </Card>
              )}
            </TabsContent>

            <TabsContent value="emerging" className="space-y-4">
              {isLoading ? (
                <p className="text-sm text-muted-foreground">Loading emerging candidates...</p>
              ) : emergingIssues.length === 0 ? (
                <Card>
                  <CardContent className="py-8 text-center text-sm text-muted-foreground">
                    No emerging candidates. Import more reviews to find emerging patterns.
                  </CardContent>
                </Card>
              ) : (
                <Card>
                  <CardContent className="p-0">
                    <div className="overflow-x-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Department</TableHead>
                            <TableHead className="text-right">Reviews</TableHead>
                            <TableHead className="text-right">Avg Similarity</TableHead>
                            <TableHead>Risk Scores</TableHead>
                            <TableHead>Snippet</TableHead>
                            <TableHead>Date Range</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {emergingIssues.map((item, idx) => (
                            <TableRow key={idx}>
                              <TableCell className="text-sm font-medium">
                                {departmentNameByCode[item.department_code] ?? item.department_code}
                              </TableCell>
                              <TableCell className="text-right text-sm">{item.review_count}</TableCell>
                              <TableCell className="text-right text-sm">
                                {item.avg_similarity != null ? (item.avg_similarity * 100).toFixed(0) + "%" : "\u2014"}
                              </TableCell>
                              <TableCell className="text-xs text-muted-foreground">
                                {item.risk_scores.join(", ")}
                              </TableCell>
                              <TableCell className="text-xs text-muted-foreground max-w-64 truncate">
                                {item.representative_snippet}
                              </TableCell>
                              <TableCell className="text-xs text-muted-foreground">
                                {formatDate(item.first_seen_at)} \u2013 {formatDate(item.last_seen_at)}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </CardContent>
                </Card>
              )}
            </TabsContent>
          </Tabs>

          {selectedIssue && (
            <IssueDetailSheet
              issue={selectedIssue}
              departmentNameByCode={departmentNameByCode}
              onClose={() => setSelectedIssue(null)}
              onResolve={resolveIssue}
            />
          )}
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
