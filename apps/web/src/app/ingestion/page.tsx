"use client"

import { Suspense, useCallback, useEffect, useState } from "react"
import { AppSidebar } from "@/components/app-sidebar"
import { SiteHeader } from "@/components/site-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import type { IngestionRun, IngestionSourceStatus } from "@/lib/api-types"
import type React from "react"

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

function formatDate(value: string | null) {
  if (!value) return "—"
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value))
}

function statusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "completed") return "default"
  if (status === "running") return "secondary"
  if (status === "failed") return "destructive"
  return "outline"
}

type TriggerDef = {
  label: string
  url: string
  method: "POST"
  sourceCode: string
  body?: Record<string, unknown>
}

const TRIGGERS: TriggerDef[] = [
  { label: "Seed dataset", url: "/ingestion/seed", method: "POST", sourceCode: "kingsbury_seed_dataset" },
  { label: "Google Business Profile", url: "/ingestion/connectors/google_business_profile", method: "POST", sourceCode: "google_business_profile" },
  { label: "Booking.com", url: "/ingestion/connectors/booking_com", method: "POST", sourceCode: "booking_com" },
  { label: "Tripadvisor", url: "/ingestion/connectors/tripadvisor", method: "POST", sourceCode: "tripadvisor" },
  { label: "Reddit", url: "/ingestion/reddit", method: "POST", sourceCode: "reddit_social_listening" },
]

function IngestionContent() {
  const [sources, setSources] = useState<IngestionSourceStatus[]>([])
  const [runs, setRuns] = useState<IngestionRun[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [triggering, setTriggering] = useState<string | null>(null)
  const [triggerResult, setTriggerResult] = useState<{ source: string; ok: boolean; message: string } | null>(null)
  const [apifyFilePath, setApifyFilePath] = useState("")
  const [apifyFileName, setApifyFileName] = useState("apify-export.json")
  const [apifyContent, setApifyContent] = useState("")

  const load = useCallback(async () => {
    setIsLoading(true)
    try {
      const [statusRes, runsRes] = await Promise.all([
        fetch(`${apiBaseUrl}/ingestion/source-status`),
        fetch(`${apiBaseUrl}/ingestion/runs`),
      ])
      if (statusRes.ok) {
        const data = await statusRes.json()
        setSources(data.sources)
      }
      if (runsRes.ok) {
        const data = await runsRes.json()
        setRuns(data.runs)
      }
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const trigger = useCallback(async (t: TriggerDef) => {
    setTriggering(t.sourceCode)
    setTriggerResult(null)
    try {
      const res = await fetch(`${apiBaseUrl}${t.url}`, {
        method: t.method,
        ...(t.body !== undefined ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(t.body) } : {}),
      })
      if (res.ok) {
        setTriggerResult({ source: t.label, ok: true, message: "Run completed successfully." })
        await load()
      } else {
        const err = await res.json().catch(() => ({ detail: "Unknown error" }))
        setTriggerResult({ source: t.label, ok: false, message: typeof err.detail === "string" ? err.detail : "Failed." })
      }
    } catch {
      setTriggerResult({ source: t.label, ok: false, message: "Network error." })
    } finally {
      setTriggering(null)
    }
  }, [load])

  const triggerApifyImport = useCallback(async () => {
    setTriggering("apify_dataset_import")
    setTriggerResult(null)
    try {
      const body = apifyContent.trim()
        ? { content: apifyContent, file_name: apifyFileName || "apify-export.json" }
        : { file_path: apifyFilePath }
      const res = await fetch(`${apiBaseUrl}/ingestion/apify-dataset`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok || payload.status === "failed") {
        const message = Array.isArray(payload.errors)
          ? payload.errors.join(", ")
          : typeof payload.detail === "string"
            ? payload.detail
            : "Failed to import Apify export."
        setTriggerResult({ source: "Apify dataset", ok: false, message })
      } else {
        const errorNote = payload.error_count > 0 ? ` ${payload.error_count} row error(s) recorded.` : ""
        setTriggerResult({
          source: "Apify dataset",
          ok: true,
          message: `Imported ${payload.records_created} new and ${payload.records_updated} updated record(s).${errorNote}`,
        })
        await load()
      }
    } catch {
      setTriggerResult({ source: "Apify dataset", ok: false, message: "Network error." })
    } finally {
      setTriggering(null)
    }
  }, [apifyContent, apifyFileName, apifyFilePath, load])

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
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Ingestion</h1>
            <p className="text-sm text-muted-foreground">
              Connector source status, run history, and manual triggers.
            </p>
          </div>

          {triggerResult && (
            <div className={`rounded-lg border px-4 py-3 text-sm ${triggerResult.ok ? "border-green-200 bg-green-50 text-green-800" : "border-destructive/30 bg-destructive/10 text-destructive"}`}>
              <span className="font-medium">{triggerResult.source}:</span> {triggerResult.message}
            </div>
          )}

          {/* Trigger buttons */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Manual triggers</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {TRIGGERS.map((t) => (
                  <Button
                    key={t.sourceCode}
                    variant="outline"
                    size="sm"
                    disabled={triggering !== null}
                    onClick={() => trigger(t)}
                    className="text-xs"
                  >
                    {triggering === t.sourceCode ? "Running…" : `Run ${t.label}`}
                  </Button>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Offline Apify import</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 lg:grid-cols-[1fr_1fr_auto]">
                <div className="flex flex-col gap-1.5">
                  <Label className="text-xs">Server file path</Label>
                  <Input
                    className="h-8 text-xs"
                    value={apifyFilePath}
                    onChange={(e) => setApifyFilePath(e.target.value)}
                    placeholder="data/imports/apify/export.json"
                    disabled={Boolean(apifyContent.trim())}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label className="text-xs">Pasted content file name</Label>
                  <Input
                    className="h-8 text-xs"
                    value={apifyFileName}
                    onChange={(e) => setApifyFileName(e.target.value)}
                    placeholder="apify-export.json or apify-export.csv"
                  />
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={triggering !== null || (!apifyFilePath && !apifyContent.trim())}
                  onClick={triggerApifyImport}
                  className="h-8 self-end text-xs"
                >
                  {triggering === "apify_dataset_import" ? "Importing..." : "Import Apify export"}
                </Button>
                <div className="flex flex-col gap-1.5 lg:col-span-3">
                  <Label className="text-xs">Pasted JSON or CSV content</Label>
                  <textarea
                    className="min-h-28 rounded-md border bg-background px-3 py-2 text-xs shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                    value={apifyContent}
                    onChange={(e) => setApifyContent(e.target.value)}
                    placeholder='[{"reviewId":"demo-001","stars":5,"reviewText":"Excellent stay."}]'
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Source status */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                {isLoading ? "Loading…" : `${sources.length} sources`}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <p className="text-sm text-muted-foreground">Loading sources…</p>
              ) : sources.length === 0 ? (
                <p className="text-sm text-muted-foreground">No sources configured.</p>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Source</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Verified</TableHead>
                        <TableHead>Last run status</TableHead>
                        <TableHead>Last run started</TableHead>
                        <TableHead>Records seen</TableHead>
                        <TableHead>Created</TableHead>
                        <TableHead>Errors</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {sources.map((s) => (
                        <TableRow key={s.source_code}>
                          <TableCell className="text-xs font-medium">{s.source_name}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">{s.source_type.replaceAll("_", " ")}</TableCell>
                          <TableCell>
                            {s.is_verified_channel ? (
                              <Badge variant="outline" className="text-xs">verified</Badge>
                            ) : (
                              <span className="text-xs text-muted-foreground">—</span>
                            )}
                          </TableCell>
                          <TableCell>
                            {s.latest_run ? (
                              <Badge variant={statusVariant(s.latest_run.status)} className="text-xs">
                                {s.latest_run.status}
                              </Badge>
                            ) : (
                              <span className="text-xs text-muted-foreground">never run</span>
                            )}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {formatDate(s.latest_run?.started_at ?? null)}
                          </TableCell>
                          <TableCell className="text-xs">
                            {s.latest_run?.records_seen ?? "—"}
                          </TableCell>
                          <TableCell className="text-xs">
                            {s.latest_run?.records_created ?? "—"}
                          </TableCell>
                          <TableCell className="text-xs">
                            {s.errors.length > 0 ? (
                              <span className="text-destructive">{s.errors.join(", ")}</span>
                            ) : (
                              <span className="text-muted-foreground">none</span>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Run history */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                {isLoading ? "Loading…" : `${runs.length} recent ${runs.length === 1 ? "run" : "runs"}`}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <p className="text-sm text-muted-foreground">Loading run history…</p>
              ) : runs.length === 0 ? (
                <p className="text-sm text-muted-foreground">No runs recorded yet.</p>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>ID</TableHead>
                        <TableHead>Connector</TableHead>
                        <TableHead>Source</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Started</TableHead>
                        <TableHead>Completed</TableHead>
                        <TableHead>Seen</TableHead>
                        <TableHead>Created</TableHead>
                        <TableHead>Updated</TableHead>
                        <TableHead>Skipped</TableHead>
                        <TableHead>Duplicates</TableHead>
                        <TableHead>Errors</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {runs.map((run) => (
                        <TableRow key={run.id}>
                          <TableCell className="text-xs text-muted-foreground">#{run.id}</TableCell>
                          <TableCell className="text-xs">{run.connector_key}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">{run.source_code}</TableCell>
                          <TableCell>
                            <Badge variant={statusVariant(run.status)} className="text-xs">{run.status}</Badge>
                          </TableCell>
                          <TableCell className="text-xs whitespace-nowrap text-muted-foreground">
                            {formatDate(run.started_at)}
                          </TableCell>
                          <TableCell className="text-xs whitespace-nowrap text-muted-foreground">
                            {formatDate(run.completed_at)}
                          </TableCell>
                          <TableCell className="text-xs">{run.records_seen}</TableCell>
                          <TableCell className="text-xs">{run.records_created}</TableCell>
                          <TableCell className="text-xs">{run.records_updated}</TableCell>
                          <TableCell className="text-xs">{run.records_skipped}</TableCell>
                          <TableCell className="text-xs">{run.records_duplicate_flagged}</TableCell>
                          <TableCell className="text-xs">
                            {run.error_count > 0 ? (
                              <span className="text-destructive">{run.error_count}</span>
                            ) : (
                              <span className="text-muted-foreground">0</span>
                            )}
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

export default function IngestionPage() {
  return (
    <Suspense>
      <IngestionContent />
    </Suspense>
  )
}
