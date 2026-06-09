"use client"

import { useCallback, useMemo } from "react"
import { useRouter, useSearchParams } from "next/navigation"

function toYmd(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${date.getFullYear()}-${month}-${day}`
}

// Rolling window: default to the last year (one year ago .. today). This keeps the newest reviews
// (including the re-stamped real crawled reviews) always in view without hardcoding a fixed range.
const ONE_YEAR_AGO = new Date()
ONE_YEAR_AGO.setFullYear(ONE_YEAR_AGO.getFullYear() - 1)

export const DEFAULT_DATE_FROM = toYmd(ONE_YEAR_AGO)
export const DEFAULT_DATE_TO = toYmd(new Date())

export type DashboardFilters = {
  source_code: string
  department_code: string
  reputation_risk: string
  risk_group: string
  has_issues: string
  search: string
  date_from: string
  date_to: string
}

const DEFAULTS: DashboardFilters = {
  source_code: "",
  department_code: "",
  reputation_risk: "",
  risk_group: "",
  has_issues: "",
  search: "",
  date_from: DEFAULT_DATE_FROM,
  date_to: DEFAULT_DATE_TO,
}

function startOfDay(value: string) {
  return `${value}T00:00:00`
}

function endOfDay(value: string) {
  return `${value}T23:59:59`
}

export function useDashboardFilters() {
  const router = useRouter()
  const searchParams = useSearchParams()

  const filters: DashboardFilters = useMemo(() => ({
    source_code: searchParams.get("source_code") ?? "",
    department_code: searchParams.get("department_code") ?? "",
    reputation_risk: searchParams.get("reputation_risk") ?? "",
    risk_group: searchParams.get("risk_group") ?? "",
    has_issues: searchParams.get("has_issues") ?? "",
    search: searchParams.get("search") ?? "",
    date_from: searchParams.get("date_from") ?? DEFAULT_DATE_FROM,
    date_to: searchParams.get("date_to") ?? DEFAULT_DATE_TO,
  }), [searchParams])

  const setFilter = useCallback((key: keyof DashboardFilters, value: string | boolean) => {
    const params = new URLSearchParams(searchParams.toString())
    const stringValue = typeof value === "boolean" ? String(value) : value
    const defaultValue = typeof DEFAULTS[key] === "boolean" ? String(DEFAULTS[key]) : DEFAULTS[key]
    if (stringValue === defaultValue || stringValue === "") {
      params.delete(key)
    } else {
      params.set(key, stringValue)
    }
    params.delete("page")
    router.push(`?${params.toString()}`, { scroll: false })
  }, [router, searchParams])

  const clearFilters = useCallback(() => {
    router.push("?", { scroll: false })
  }, [router])

  const buildApiParams = useCallback((extraParams?: Record<string, string>) => {
    const params = new URLSearchParams()
    if (filters.source_code) params.set("source_code", filters.source_code)
    if (filters.department_code) params.set("department_code", filters.department_code)
    if (filters.reputation_risk) params.set("reputation_risk", filters.reputation_risk)
    if (filters.risk_group) params.set("risk_group", filters.risk_group)
    if (filters.has_issues) params.set("has_issues", filters.has_issues)
    if (filters.search) params.set("search", filters.search)
    if (filters.date_from) params.set("date_from", startOfDay(filters.date_from))
    if (filters.date_to) params.set("date_to", endOfDay(filters.date_to))
    if (extraParams) {
      for (const [key, value] of Object.entries(extraParams)) {
        params.set(key, value)
      }
    }
    return params
  }, [filters])

  const hasActiveFilters = Object.entries(filters).some(([key, value]) => {
    return value !== (DEFAULTS as Record<string, unknown>)[key]
  })

  return { filters, setFilter, clearFilters, buildApiParams, hasActiveFilters }
}
