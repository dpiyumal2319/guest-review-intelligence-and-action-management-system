"use client"

import { useCallback, useMemo } from "react"
import { useRouter, useSearchParams } from "next/navigation"

export type DashboardFilters = {
  source_code: string
  issue_category_code: string
  department_code: string
  sentiment_label: string
  reputation_risk: string
  action_status: string
  search: string
  date_from: string
  date_to: string
}

const DEFAULTS: DashboardFilters = {
  source_code: "",
  issue_category_code: "",
  department_code: "",
  sentiment_label: "",
  reputation_risk: "",
  action_status: "",
  search: "",
  date_from: "",
  date_to: "",
}

export function useDashboardFilters() {
  const router = useRouter()
  const searchParams = useSearchParams()

  const filters: DashboardFilters = useMemo(() => ({
    source_code: searchParams.get("source_code") ?? "",
    issue_category_code: searchParams.get("issue_category_code") ?? "",
    department_code: searchParams.get("department_code") ?? "",
    sentiment_label: searchParams.get("sentiment_label") ?? "",
    reputation_risk: searchParams.get("reputation_risk") ?? "",
    action_status: searchParams.get("action_status") ?? "",
    search: searchParams.get("search") ?? "",
    date_from: searchParams.get("date_from") ?? "",
    date_to: searchParams.get("date_to") ?? "",
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
    router.push(`?${params.toString()}`, { scroll: false })
  }, [router, searchParams])

  const clearFilters = useCallback(() => {
    router.push("?", { scroll: false })
  }, [router])

  const buildApiParams = useCallback((extraParams?: Record<string, string>) => {
    const params = new URLSearchParams()
    if (filters.source_code) params.set("source_code", filters.source_code)
    if (filters.issue_category_code) params.set("issue_category_code", filters.issue_category_code)
    if (filters.department_code) params.set("department_code", filters.department_code)
    if (filters.sentiment_label) params.set("sentiment_label", filters.sentiment_label)
    if (filters.reputation_risk) params.set("reputation_risk", filters.reputation_risk)
    if (filters.action_status) params.set("action_status", filters.action_status)
    if (filters.search) params.set("search", filters.search)
    if (filters.date_from) params.set("date_from", filters.date_from)
    if (filters.date_to) params.set("date_to", filters.date_to)
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
