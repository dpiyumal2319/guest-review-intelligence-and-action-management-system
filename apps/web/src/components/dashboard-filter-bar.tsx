"use client"

import { SearchIcon, XIcon } from "lucide-react"
import { type Department, type ReviewSource, REPUTATION_RISK_LABELS } from "@/lib/api-types"
import { type DashboardFilters } from "@/hooks/use-dashboard-filters"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

type Props = {
  filters: DashboardFilters
  onFilterChange: (key: keyof DashboardFilters, value: string | boolean) => void
  onClear: () => void
  hasActiveFilters: boolean
  sources?: ReviewSource[]
  departments?: Department[]
  showSearch?: boolean
  showRiskGroup?: boolean
  showHasIssues?: boolean
}

const NONE = "__none__"

function toSelectValue(value: string): string | null {
  return value === "" ? NONE : value
}

function fromSelectValue(value: string | null): string {
  return value === NONE || value === null ? "" : value
}

function filterSelectValueLabel(emptyLabel: string, labels: Record<string, string> = {}) {
  return (value: string | null) => {
    if (value === NONE || value === null) return emptyLabel
    return labels[value] ?? value
  }
}

export function DashboardFilterBar({
  filters,
  onFilterChange,
  onClear,
  hasActiveFilters,
  sources = [],
  departments = [],
  showSearch = false,
  showRiskGroup = false,
  showHasIssues = false,
}: Props) {
  const sourceLabels = Object.fromEntries(sources.map((source) => [source.code, source.name]))
  const departmentLabels = Object.fromEntries(departments.map((department) => [department.code, department.name]))

  return (
    <div className="flex flex-wrap items-end gap-3 rounded-lg border bg-card p-4">
      {showSearch && (
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs">Search</Label>
          <div className="relative">
            <SearchIcon className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="search"
              className="h-8 w-56 pl-7 text-xs"
              value={filters.search}
              onChange={(e) => onFilterChange("search", e.target.value)}
              placeholder="Review, title, guest, ID"
            />
          </div>
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        <Label className="text-xs">Date from</Label>
        <Input
          type="date"
          className="h-8 w-36 text-xs"
          value={filters.date_from}
          onChange={(e) => onFilterChange("date_from", e.target.value)}
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label className="text-xs">Date to</Label>
        <Input
          type="date"
          className="h-8 w-36 text-xs"
          value={filters.date_to}
          onChange={(e) => onFilterChange("date_to", e.target.value)}
        />
      </div>

      {sources.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs">Review platform</Label>
          <Select
            value={toSelectValue(filters.source_code)}
            onValueChange={(v) => onFilterChange("source_code", fromSelectValue(v))}
          >
            <SelectTrigger className="h-8 w-44 text-xs">
              <SelectValue>{filterSelectValueLabel("All platforms", sourceLabels)}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>All platforms</SelectItem>
              {sources.map((s) => (
                <SelectItem key={s.code} value={s.code}>{s.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {departments.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs">Owner department</Label>
          <Select
            value={toSelectValue(filters.department_code)}
            onValueChange={(v) => onFilterChange("department_code", fromSelectValue(v))}
          >
            <SelectTrigger className="h-8 w-44 text-xs">
              <SelectValue>{filterSelectValueLabel("Any department", departmentLabels)}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>Any department</SelectItem>
              {departments.map((d) => (
                <SelectItem key={d.code} value={d.code}>{d.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        <Label className="text-xs">Reputation Risk</Label>
        <Select
          value={toSelectValue(filters.reputation_risk)}
          onValueChange={(v) => onFilterChange("reputation_risk", fromSelectValue(v))}
        >
          <SelectTrigger className="h-8 w-36 text-xs">
            <SelectValue>{filterSelectValueLabel("Any risk")}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NONE}>Any risk</SelectItem>
            {REPUTATION_RISK_LABELS.map((l) => (
              <SelectItem key={l} value={l}>{l} risk</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {showRiskGroup && (
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs">Risk group</Label>
          <Select
            value={toSelectValue(filters.risk_group)}
            onValueChange={(v) => onFilterChange("risk_group", fromSelectValue(v))}
          >
            <SelectTrigger className="h-8 w-40 text-xs">
              <SelectValue>{filterSelectValueLabel("Any group", { high_or_critical: "High or critical" })}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>Any group</SelectItem>
              <SelectItem value="high_or_critical">High or critical</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}

      {showHasIssues && (
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs">Issue linkage</Label>
          <Select
            value={toSelectValue(filters.has_issues)}
            onValueChange={(v) => onFilterChange("has_issues", fromSelectValue(v))}
          >
            <SelectTrigger className="h-8 w-40 text-xs">
              <SelectValue>{filterSelectValueLabel("Any", { true: "Linked to Issues", false: "No Issues" })}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>Any</SelectItem>
              <SelectItem value="true">Linked to Issues</SelectItem>
              <SelectItem value="false">No Issues</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}

      {hasActiveFilters && (
        <Button variant="ghost" size="sm" className="h-8 gap-1.5 text-xs" onClick={onClear}>
          <XIcon className="size-3" />
          Clear
        </Button>
      )}
    </div>
  )
}
