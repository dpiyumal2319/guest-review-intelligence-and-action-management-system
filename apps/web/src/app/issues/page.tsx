"use client"

import { Suspense, useCallback, useEffect, useState } from "react"
import { AppSidebar } from "@/components/app-sidebar"
import { SiteHeader } from "@/components/site-header"
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

        <div className="flex flex-wrap gap-2 mb-4">
          <Badge variant={statusBadgeVariant(issue.status)}>{issue.status}</Badge>
          <Badge variant={riskBadgeVariant(issue.reputation_risk_score)}>
            Risk: {issue.reputation_risk_score}
          </Badge>
          <Badge variant="outline">Priority: {issue.priority}</Badge>
          <Badge variant="outline">Recurrence: {issue.recurrence_count}x</Badge>
        </div>

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
  const { activeRole, scopeLabel } = useDemoRole()
  const [departments, setDepartments] = useState<Department[]>([])
  const [activeIssues, setActiveIssues] = useState<IssuesResponse | null>(null)
  const [emergingIssues, setEmergingIssues] = useState<IssueEmerging[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedIssue, setSelectedIssue] = useState<DetectedIssue | null>(null)
  const [activeTab, setActiveTab] = useState("active")

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
      const [issuesRes, emergingRes] = await Promise.all([
        fetch(`${apiBaseUrl}/issues?per_page=500`),
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
  }, [])

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

          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList>
              <TabsTrigger value="active">
                Active Issues
                {activeIssues && (
                  <Badge variant="secondary" className="ml-2 text-xs">
                    {activeIssues.issues.filter((i) => i.status === "active" || i.status === "recurred").length}
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
                              <TableCell className="font-medium text-sm max-w-48 truncate">
                                {issue.title}
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
