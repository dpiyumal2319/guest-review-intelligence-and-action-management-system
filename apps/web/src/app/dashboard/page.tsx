"use client"

import type * as React from "react"
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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
  { label: "Verified reviews", value: "1,248", detail: "+14% this month" },
  { label: "Negative sentiment", value: "18%", detail: "verified sources only" },
  { label: "High severity", value: "37", detail: "needs review" },
  { label: "Open tickets", value: "22", detail: "7 waiting on department" },
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

export default function Page() {
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
            {metrics.map((metric) => (
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
              <Card key={queue.title} id={queue.id}>
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
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
