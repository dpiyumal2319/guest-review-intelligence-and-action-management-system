"use client"

import { Suspense, useCallback, useEffect, useState } from "react"
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { useDashboardFilters } from "@/hooks/use-dashboard-filters"
import { useDemoRole } from "@/hooks/use-demo-role"
import { TICKET_PRIORITIES, type Department, type IssueCategory, type ReviewSource, type Ticket, type TicketEvent } from "@/lib/api-types"
import type React from "react"

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
const TICKET_STATUS_TRANSITIONS: Record<string, string[]> = {
  open: ["open", "in_progress", "blocked", "resolved"],
  in_progress: ["in_progress", "open", "blocked", "resolved"],
  blocked: ["blocked", "open", "in_progress", "resolved"],
  resolved: ["resolved", "open", "in_progress", "blocked", "verified"],
  verified: ["verified"],
}

function formatDate(value: string | null) {
  if (!value) return "—"
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value))
}

function formatDateTime(value: string | null) {
  if (!value) return "—"
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value))
}

function priorityVariant(priority: string): "default" | "secondary" | "destructive" | "outline" {
  if (priority === "urgent") return "destructive"
  if (priority === "high") return "destructive"
  if (priority === "medium") return "secondary"
  return "outline"
}

function statusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "resolved" || status === "verified") return "default"
  if (status === "blocked") return "destructive"
  if (status === "in_progress") return "secondary"
  return "outline"
}

function eventTypeLabel(eventType: string): string {
  const labels: Record<string, string> = {
    created: "created",
    status_change: "status changed",
    priority_change: "priority changed",
    department_change: "department reassigned",
    assignment_change: "assignee updated",
    note_added: "note added",
    due_date_change: "due date updated",
  }
  return labels[eventType] ?? eventType.replaceAll("_", " ")
}

function ticketSourceLabel(ticket: Ticket, categoryNameByCode: Record<string, string>): string {
  if (ticket.source_group_type === "category_department_recurrence" && ticket.source_category_code) {
    return `${categoryNameByCode[ticket.source_category_code] ?? ticket.source_category_code.replaceAll("_", " ")} recurrence`
  }
  if (ticket.source_group_type === "semantic_cluster" && ticket.source_cluster_id) {
    const category = ticket.source_category_code
      ? categoryNameByCode[ticket.source_category_code] ?? ticket.source_category_code.replaceAll("_", " ")
      : "Semantic"
    return `${category} cluster ${ticket.source_cluster_id}`
  }
  return ticket.review_id ? `Review #${ticket.review_id}` : "Unlinked ticket"
}

function TicketDetailSheet({
  ticket,
  open,
  onOpenChange,
  onTicketSaved,
  departments,
  departmentNameByCode,
  categoryNameByCode,
  canManageTickets,
}: {
  ticket: Ticket | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onTicketSaved: (ticket: Ticket) => void
  departments: Department[]
  departmentNameByCode: Record<string, string>
  categoryNameByCode: Record<string, string>
  canManageTickets: boolean
}) {
  const [status, setStatus] = useState("")
  const [priority, setPriority] = useState("")
  const [departmentCode, setDepartmentCode] = useState("")
  const [assigneeName, setAssigneeName] = useState("")
  const [assigneeEmail, setAssigneeEmail] = useState("")
  const [dueDate, setDueDate] = useState("")
  const [notes, setNotes] = useState("")
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    if (!ticket) return
    setStatus(ticket.status)
    setPriority(ticket.priority)
    setDepartmentCode(ticket.department_code)
    setAssigneeName(ticket.assignee_name ?? "")
    setAssigneeEmail(ticket.assignee_email ?? "")
    setDueDate(ticket.due_date ? ticket.due_date.slice(0, 10) : "")
    setNotes("")
    setSaveError(null)
  }, [ticket])

  if (!ticket) return null

  const sortedEvents = [...ticket.events].sort(
    (a, b) => new Date(a.occurred_at).getTime() - new Date(b.occurred_at).getTime()
  )
  const availableStatuses = TICKET_STATUS_TRANSITIONS[ticket.status] ?? [ticket.status]
  const noteLabel = status === "resolved"
    ? "Resolution note"
    : status === "verified"
      ? "Verification note"
      : "Workflow note"
  const notePlaceholder = status === "resolved"
    ? "Describe the corrective action that resolved the issue."
    : status === "verified"
      ? "Record what was checked before marking the ticket verified."
      : "Add context for the next owner or reviewer."

  async function saveTicketUpdates() {
    if (!ticket || !canManageTickets) return
    setIsSaving(true)
    setSaveError(null)
    try {
      const res = await fetch(`${apiBaseUrl}/tickets/${ticket.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status,
          priority,
          department_code: departmentCode,
          assignee_name: assigneeName || null,
          assignee_email: assigneeEmail || null,
          due_date: dueDate ? new Date(`${dueDate}T00:00:00`).toISOString() : null,
          notes: notes || null,
        }),
      })
      if (!res.ok) {
        const errorPayload = await res.json().catch(() => ({ detail: "Failed to update ticket" }))
        throw new Error(errorPayload.detail ?? "Failed to update ticket")
      }
      const updated = await res.json()
      onTicketSaved(updated)
      setNotes("")
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to update ticket")
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-lg overflow-y-auto">
        <SheetHeader className="pb-4">
          <SheetTitle>Ticket #{ticket.id}</SheetTitle>
          <SheetDescription>
            {ticketSourceLabel(ticket, categoryNameByCode)}
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-col gap-4 px-4 pb-4">
          <div className="rounded-md border p-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs">Status</Label>
                <Select value={status} onValueChange={(value) => value && setStatus(value)} disabled={!canManageTickets}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {availableStatuses.map((item) => (
                      <SelectItem key={item} value={item}>{item.replaceAll("_", " ")}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs">Priority</Label>
                <Select value={priority} onValueChange={(value) => value && setPriority(value)} disabled={!canManageTickets}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TICKET_PRIORITIES.map((item) => (
                      <SelectItem key={item} value={item}>{item}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs">Department</Label>
                <Select value={departmentCode} onValueChange={(value) => value && setDepartmentCode(value)} disabled={!canManageTickets}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {departments.map((department) => (
                      <SelectItem key={department.code} value={department.code}>{department.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs">Due date</Label>
                <Input type="date" className="h-8 text-xs" value={dueDate} onChange={(e) => setDueDate(e.target.value)} disabled={!canManageTickets} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs">Assignee</Label>
                <Input className="h-8 text-xs" value={assigneeName} onChange={(e) => setAssigneeName(e.target.value)} disabled={!canManageTickets} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs">Assignee email</Label>
                <Input className="h-8 text-xs" value={assigneeEmail} onChange={(e) => setAssigneeEmail(e.target.value)} disabled={!canManageTickets} />
              </div>
              <div className="flex flex-col gap-1.5 sm:col-span-2">
                <Label className="text-xs">{noteLabel}</Label>
                <textarea
                  className="min-h-20 rounded-md border bg-background px-3 py-2 text-xs shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  disabled={!canManageTickets}
                  placeholder={notePlaceholder}
                />
              </div>
            </div>
            {saveError && <p className="mt-2 text-xs text-destructive">{saveError}</p>}
            {canManageTickets ? (
              <Button size="sm" className="mt-3 h-8 text-xs" disabled={isSaving} onClick={saveTicketUpdates}>
                {isSaving ? "Saving..." : "Save updates"}
              </Button>
            ) : (
              <p className="mt-3 text-xs text-muted-foreground">
                This demo role can inspect ticket history but cannot edit ticket workflow fields.
              </p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-xs text-muted-foreground">Source</p>
              <p className="font-medium">{ticketSourceLabel(ticket, categoryNameByCode)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Department</p>
              <p className="font-medium">
                {departmentNameByCode[ticket.department_code] ?? ticket.department_code.replaceAll("_", " ")}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Priority</p>
              <Badge variant={priorityVariant(ticket.priority)} className="text-xs mt-0.5">
                {ticket.priority}
              </Badge>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Status</p>
              <Badge variant={statusVariant(ticket.status)} className="text-xs mt-0.5">
                {ticket.status.replaceAll("_", " ")}
              </Badge>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Assignee</p>
              <p className="font-medium">{ticket.assignee_name ?? ticket.assignee_email ?? "—"}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Created</p>
              <p className="font-medium">{formatDate(ticket.created_at)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Due date</p>
              <p className="font-medium">{formatDate(ticket.due_date)}</p>
            </div>
          </div>

          {ticket.notes && (
            <div>
              <p className="text-xs text-muted-foreground mb-1">Notes</p>
              <p className="text-sm rounded-md border bg-muted/40 p-3">{ticket.notes}</p>
            </div>
          )}

          {ticket.source_review_ids && ticket.source_review_ids.length > 0 && (
            <div>
              <p className="text-xs text-muted-foreground mb-1">Source reviews</p>
              <p className="text-sm rounded-md border bg-muted/40 p-3">
                {ticket.source_review_ids.map((id) => `#${id}`).join(", ")}
              </p>
            </div>
          )}

          <div>
            <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wide">
              Event history
            </p>
            {sortedEvents.length === 0 ? (
              <p className="text-sm text-muted-foreground">No events recorded.</p>
            ) : (
              <ol className="relative border-l border-border ml-2 flex flex-col gap-4">
                {sortedEvents.map((event: TicketEvent) => (
                  <li key={event.id} className="ml-4">
                    <div className="absolute -left-1.5 mt-1.5 size-3 rounded-full border bg-background" />
                    <p className="text-xs text-muted-foreground">{formatDateTime(event.occurred_at)}</p>
                    <p className="text-sm font-medium capitalize">{eventTypeLabel(event.event_type)}</p>
                    {(event.old_value || event.new_value) && (
                      <p className="text-xs text-muted-foreground">
                        {event.old_value && <span className="line-through mr-1">{event.old_value}</span>}
                        {event.new_value && <span>{event.new_value}</span>}
                      </p>
                    )}
                    {event.note && (
                      <p className="text-xs text-muted-foreground italic mt-0.5">{event.note}</p>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}

function TicketsContent() {
  const { filters, setFilter, clearFilters, buildApiParams, hasActiveFilters } = useDashboardFilters()
  const { activeRole, canManageTickets, departments: scopedDepartments, effectiveDepartmentCode, scopeLabel } = useDemoRole()
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [categories, setCategories] = useState<IssueCategory[]>([])
  const [sources, setSources] = useState<ReviewSource[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null)
  const [sheetOpen, setSheetOpen] = useState(false)

  const loadConfig = useCallback(async () => {
    const res = await fetch(`${apiBaseUrl}/config`)
    if (!res.ok) return
    const data = await res.json()
    setDepartments(data.departments)
    setCategories(data.issue_categories)
    setSources(data.review_sources)
  }, [])

  const loadTickets = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const params = buildApiParams()
      if (!params.get("department_code") && effectiveDepartmentCode) {
        params.set("department_code", effectiveDepartmentCode)
      }
      const res = await fetch(`${apiBaseUrl}/tickets?${params}`)
      if (!res.ok) throw new Error("Failed to load tickets")
      const data = await res.json()
      setTickets(data.tickets)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load tickets")
    } finally {
      setIsLoading(false)
    }
  }, [buildApiParams, effectiveDepartmentCode])

  useEffect(() => { loadConfig() }, [loadConfig])
  useEffect(() => { loadTickets() }, [loadTickets])

  const departmentNameByCode = Object.fromEntries(departments.map((d) => [d.code, d.name]))
  const categoryNameByCode = Object.fromEntries(categories.map((c) => [c.code, c.name]))
  const scopedDepartmentName = scopedDepartments.find((department) => department.code === effectiveDepartmentCode)?.name

  function handleRowClick(ticket: Ticket) {
    setSelectedTicket(ticket)
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
              <h1 className="text-2xl font-semibold tracking-tight">Tickets</h1>
              <p className="text-sm text-muted-foreground">
                Action tickets linked to guest reviews. Filter by ticket fields or the underlying review.
              </p>
              {activeRole && (
                <div className="mt-2 flex flex-wrap gap-2">
                  <Badge variant="outline" className="text-xs">{activeRole.name}</Badge>
                  <Badge variant="secondary" className="text-xs">{scopeLabel}</Badge>
                  <Badge variant={canManageTickets ? "secondary" : "outline"} className="text-xs">
                    {canManageTickets ? "Ticket edits enabled" : "Read-only ticket access"}
                  </Badge>
                  {effectiveDepartmentCode && !filters.department_code && scopedDepartmentName && (
                    <Badge variant="outline" className="text-xs">
                      Defaulting to {scopedDepartmentName}
                    </Badge>
                  )}
                </div>
              )}
            </div>
            {!isLoading && (
              <Badge variant="outline">{tickets.length} {tickets.length === 1 ? "ticket" : "tickets"}</Badge>
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
                {isLoading ? "Loading…" : error ? "Error" : `${tickets.length} tickets`}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {error ? (
                <p className="text-sm text-destructive">{error}</p>
              ) : isLoading ? (
                <p className="text-sm text-muted-foreground">Loading tickets…</p>
              ) : tickets.length === 0 ? (
                <p className="text-sm text-muted-foreground">No tickets match the current filters.</p>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Created</TableHead>
                        <TableHead>Department</TableHead>
                        <TableHead>Priority</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Assignee</TableHead>
                        <TableHead>Source</TableHead>
                        <TableHead>Due date</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {tickets.map((ticket) => (
                        <TableRow
                          key={ticket.id}
                          className="cursor-pointer"
                          onClick={() => handleRowClick(ticket)}
                        >
                          <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                            {formatDate(ticket.created_at)}
                          </TableCell>
                          <TableCell className="text-xs">
                            {departmentNameByCode[ticket.department_code] ?? ticket.department_code.replaceAll("_", " ")}
                          </TableCell>
                          <TableCell>
                            <Badge variant={priorityVariant(ticket.priority)} className="text-xs">
                              {ticket.priority}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge variant={statusVariant(ticket.status)} className="text-xs">
                              {ticket.status.replaceAll("_", " ")}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs">
                            {ticket.assignee_name ?? ticket.assignee_email ?? "—"}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {ticketSourceLabel(ticket, categoryNameByCode)}
                          </TableCell>
                          <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                            {formatDate(ticket.due_date)}
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

      <TicketDetailSheet
        ticket={selectedTicket}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        onTicketSaved={(ticket) => {
          setSelectedTicket(ticket)
          setTickets((current) => current.map((item) => item.id === ticket.id ? ticket : item))
          void loadTickets()
        }}
        departments={departments}
        departmentNameByCode={departmentNameByCode}
        categoryNameByCode={categoryNameByCode}
        canManageTickets={canManageTickets}
      />
    </SidebarProvider>
  )
}

export default function TicketsPage() {
  return (
    <Suspense>
      <TicketsContent />
    </Suspense>
  )
}
