"use client"

import type * as React from "react"
import { useEffect, useMemo, useState } from "react"
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  XAxis,
} from "recharts"

import { AppSidebar } from "@/components/app-sidebar"
import { SiteHeader } from "@/components/site-header"
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
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"

const trendData = [
  { day: "Mon", positive: 34, negative: 9 },
  { day: "Tue", positive: 28, negative: 14 },
  { day: "Wed", positive: 41, negative: 12 },
  { day: "Thu", positive: 36, negative: 18 },
  { day: "Fri", positive: 49, negative: 16 },
  { day: "Sat", positive: 56, negative: 21 },
  { day: "Sun", positive: 44, negative: 13 },
]

const issueData = [
  { category: "Cleanliness", count: 31 },
  { category: "Service", count: 27 },
  { category: "Room", count: 22 },
  { category: "F&B", count: 18 },
  { category: "Noise", count: 12 },
]

const trendConfig = {
  positive: {
    label: "Positive",
    color: "var(--chart-1)",
  },
  negative: {
    label: "Negative",
    color: "var(--chart-3)",
  },
} satisfies ChartConfig

const issueConfig = {
  count: {
    label: "Reviews",
    color: "var(--chart-2)",
  },
} satisfies ChartConfig

const metrics = [
  { label: "Verified reviews", value: "1,248", detail: "mock baseline" },
  { label: "Negative sentiment", value: "18%", detail: "verified sources only" },
]

const queues = [
  {
    title: "Reviews",
    id: "reviews",
    body: "Searchable normalized review queue with source, rating, sentiment, category, severity, and action status filters.",
    status: "Shell ready",
  },
  {
    title: "Issues",
    id: "issues",
    body: "Recurring issue categories and semantic clusters will surface operational patterns before ticket creation.",
    status: "Awaiting pipeline",
  },
  {
    title: "Tickets",
    id: "tickets",
    body: "Department-owned corrective actions will track priority, status, notes, resolution, and verification.",
    status: "Workflow next",
  },
  {
    title: "Ingestion",
    id: "ingestion",
    body: "Manual connector runs for mock verified sources, Reddit social listening, fallback seed, and Apify dataset files.",
    status: "API hook next",
  },
]

type Review = {
  id: number
  source_code: string
  external_review_id: string
  reviewer_name: string | null
  review_date: string | null
  rating: number | null
  title: string | null
  body: string
  sentiment_label: string
  issue_category_code: string
  severity: string
  department_code: string
  action_status: string
}

type IngestionRun = {
  id: number
  connector_key: string
  source_code: string
  status: string
  started_at: string
  completed_at: string | null
  records_seen: number
  records_created: number
  records_updated: number
  records_skipped: number
  error_count: number
  errors: string[]
}

type IngestionSourceStatus = {
  source_code: string
  source_name: string
  connector_key: string | null
  source_type: string
  is_verified_channel: boolean
  latest_run: IngestionRun | null
  errors: string[]
}

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

function formatDate(value: string | null) {
  if (!value) {
    return "Not recorded"
  }
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value))
}

export default function Page() {
  const [reviews, setReviews] = useState<Review[]>([])
  const [runs, setRuns] = useState<IngestionRun[]>([])
  const [sourceStatuses, setSourceStatuses] = useState<IngestionSourceStatus[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isImporting, setIsImporting] = useState(false)
  const [importingConnector, setImportingConnector] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const latestRun = runs[0]
  const verifiedSourceStatuses = useMemo(
    () => sourceStatuses.filter((source) => source.is_verified_channel && source.connector_key),
    [sourceStatuses]
  )
  const importedMetrics = useMemo(
    () => [
      ...metrics,
      {
        label: "Imported seed reviews",
        value: reviews.length.toString(),
        detail: latestRun ? `last run ${latestRun.status}` : "awaiting import",
      },
      {
        label: "High severity",
        value: reviews.filter((review) => review.severity === "high").length.toString(),
        detail: "from imported reviews",
      },
    ],
    [latestRun, reviews]
  )

  async function loadIngestionData() {
    setError(null)
    const [reviewsResponse, runsResponse, sourceStatusResponse] = await Promise.all([
      fetch(`${apiBaseUrl}/reviews`),
      fetch(`${apiBaseUrl}/ingestion/runs`),
      fetch(`${apiBaseUrl}/ingestion/source-status`),
    ])
    if (!reviewsResponse.ok || !runsResponse.ok || !sourceStatusResponse.ok) {
      throw new Error("Unable to load review ingestion data")
    }
    const reviewsPayload = await reviewsResponse.json()
    const runsPayload = await runsResponse.json()
    const sourceStatusPayload = await sourceStatusResponse.json()
    setReviews(reviewsPayload.reviews)
    setRuns(runsPayload.runs)
    setSourceStatuses(sourceStatusPayload.sources)
  }

  useEffect(() => {
    loadIngestionData()
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Unable to load data"))
      .finally(() => setIsLoading(false))
  }, [])

  async function triggerSeedImport() {
    setIsImporting(true)
    setError(null)
    try {
      const response = await fetch(`${apiBaseUrl}/ingestion/seed`, { method: "POST" })
      if (!response.ok) {
        throw new Error("Seed import failed")
      }
      await loadIngestionData()
    } catch (importError) {
      setError(importError instanceof Error ? importError.message : "Seed import failed")
    } finally {
      setIsImporting(false)
    }
  }

  async function triggerConnectorImport(connectorKey: string) {
    setImportingConnector(connectorKey)
    setError(null)
    try {
      const response = await fetch(`${apiBaseUrl}/ingestion/connectors/${connectorKey}`, { method: "POST" })
      if (!response.ok) {
        throw new Error(`${connectorKey} import failed`)
      }
      await loadIngestionData()
    } catch (importError) {
      setError(importError instanceof Error ? importError.message : `${connectorKey} import failed`)
    } finally {
      setImportingConnector(null)
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
        <main className="flex flex-1 flex-col gap-6 p-4 md:p-6">
          <section className="grid gap-4 lg:grid-cols-[1.25fr_0.75fr]">
            <div className="rounded-lg border bg-card p-6 shadow-sm">
              <Badge variant="outline" className="mb-4">
                Kingsbury case study
              </Badge>
              <h2 className="max-w-3xl text-3xl font-semibold tracking-tight">
                Guest review intelligence and action management
              </h2>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
                A focused dashboard shell for reviewing verified guest feedback,
                separating social listening signals, spotting recurring service
                issues, and turning priority findings into department-owned
                action tickets.
              </p>
            </div>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Source policy</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-muted-foreground">
                <p>Verified KPIs use Google Business Profile, Booking.com, and Tripadvisor mock connectors.</p>
                <p>Reddit remains social listening and is excluded from default verified-review KPIs.</p>
              </CardContent>
            </Card>
          </section>

          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {importedMetrics.map((metric) => (
              <Card key={metric.label}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    {metric.label}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-semibold">{metric.value}</div>
                  <p className="mt-1 text-xs text-muted-foreground">{metric.detail}</p>
                </CardContent>
              </Card>
            ))}
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Sentiment trend</CardTitle>
              </CardHeader>
              <CardContent>
                <ChartContainer config={trendConfig} className="h-72 w-full">
                  <AreaChart data={trendData}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="day" tickLine={false} axisLine={false} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Area dataKey="positive" type="natural" fill="var(--color-positive)" fillOpacity={0.25} stroke="var(--color-positive)" />
                    <Area dataKey="negative" type="natural" fill="var(--color-negative)" fillOpacity={0.2} stroke="var(--color-negative)" />
                  </AreaChart>
                </ChartContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Recurring issue categories</CardTitle>
              </CardHeader>
              <CardContent>
                <ChartContainer config={issueConfig} className="h-72 w-full">
                  <BarChart data={issueData}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="category" tickLine={false} axisLine={false} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Bar dataKey="count" fill="var(--color-count)" radius={6} />
                  </BarChart>
                </ChartContainer>
              </CardContent>
            </Card>
          </section>

          <section className="grid gap-4 xl:grid-cols-4">
            {queues.map((queue) => (
              <Card key={queue.title}>
                <CardHeader>
                  <div className="flex items-center justify-between gap-3">
                    <CardTitle>{queue.title}</CardTitle>
                    <Badge variant="secondary">{queue.status}</Badge>
                  </div>
                </CardHeader>
                <CardContent className="text-sm leading-6 text-muted-foreground">
                  {queue.body}
                </CardContent>
              </Card>
            ))}
          </section>

          <section id="ingestion" className="grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <CardTitle>Verified source imports</CardTitle>
                  <Button onClick={triggerSeedImport} disabled={isImporting}>
                    {isImporting ? "Importing" : "Run seed import"}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                {error ? <p className="text-destructive">{error}</p> : null}
                {isLoading ? (
                  <p className="text-muted-foreground">Loading ingestion status.</p>
                ) : verifiedSourceStatuses.length > 0 ? (
                  <div className="space-y-3">
                    {verifiedSourceStatuses.map((source) => {
                      const run = source.latest_run
                      const connectorKey = source.connector_key ?? ""
                      const hasErrors = source.errors.length > 0
                      return (
                        <div key={source.source_code} className="rounded-md border p-3">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <p className="font-medium">{source.source_name}</p>
                              <p className="text-xs text-muted-foreground">{connectorKey}</p>
                            </div>
                            <div className="flex items-center gap-2">
                              <Badge variant={run?.status === "completed" ? "secondary" : hasErrors ? "destructive" : "outline"}>
                                {run?.status ?? "not run"}
                              </Badge>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => triggerConnectorImport(connectorKey)}
                                disabled={importingConnector === connectorKey}
                              >
                                {importingConnector === connectorKey ? "Importing" : "Run"}
                              </Button>
                            </div>
                          </div>
                          {run ? (
                            <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
                              <p>Completed: {formatDate(run.completed_at)}</p>
                              <p>
                                {run.records_seen} seen, {run.records_created} created, {run.records_updated} updated,{" "}
                                {run.records_skipped} skipped
                              </p>
                            </div>
                          ) : (
                            <p className="mt-3 text-xs text-muted-foreground">No import run recorded for this source.</p>
                          )}
                          {hasErrors ? (
                            <div className="mt-3 space-y-1 text-xs text-destructive">
                              {source.errors.map((sourceError) => (
                                <p key={sourceError}>{sourceError}</p>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <p className="text-muted-foreground">No ingestion runs yet.</p>
                )}
              </CardContent>
            </Card>

            <Card id="reviews">
              <CardHeader>
                <CardTitle>Imported reviews</CardTitle>
              </CardHeader>
              <CardContent>
                {reviews.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Run the seed import to populate normalized reviews.
                  </p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Review</TableHead>
                        <TableHead>Rating</TableHead>
                        <TableHead>Category</TableHead>
                        <TableHead>Department</TableHead>
                        <TableHead>Severity</TableHead>
                        <TableHead>Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {reviews.map((review) => (
                        <TableRow key={review.id}>
                          <TableCell className="min-w-80 whitespace-normal">
                            <div className="font-medium">{review.title ?? review.external_review_id}</div>
                            <div className="text-xs text-muted-foreground">
                              {review.reviewer_name ?? "Anonymous"} · {formatDate(review.review_date)}
                            </div>
                            <p className="mt-1 max-h-10 overflow-hidden text-sm text-muted-foreground">{review.body}</p>
                          </TableCell>
                          <TableCell>{review.rating ?? "N/A"}</TableCell>
                          <TableCell>{review.issue_category_code}</TableCell>
                          <TableCell>{review.department_code}</TableCell>
                          <TableCell>
                            <Badge variant={review.severity === "high" ? "destructive" : "outline"}>
                              {review.severity}
                            </Badge>
                          </TableCell>
                          <TableCell>{review.action_status}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </section>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
