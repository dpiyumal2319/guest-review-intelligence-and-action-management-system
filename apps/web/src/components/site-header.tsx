"use client"

import { useDemoRole } from "@/hooks/use-demo-role"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"

export function SiteHeader() {
  const {
    activeRole,
    activeRoleCode,
    assignedDepartmentCode,
    canManageTickets,
    departments,
    isLoading,
    roles,
    scopeLabel,
    setActiveRoleCode,
    setAssignedDepartmentCode,
    workflowLabel,
  } = useDemoRole()
  const roleLabels = Object.fromEntries(roles.map((role) => [role.code, role.name]))
  const departmentLabels = Object.fromEntries(departments.map((department) => [department.code, department.name]))

  return (
    <header className="flex min-h-(--header-height) shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear md:h-(--header-height) group-has-data-[collapsible=icon]/sidebar-wrapper:md:h-(--header-height)">
      <div className="flex w-full min-w-0 flex-wrap items-center gap-3 px-4 py-2 md:h-full md:flex-nowrap md:py-0 lg:gap-4 lg:px-6">
        <SidebarTrigger className="-ml-1" />
        <Separator
          orientation="vertical"
          className="mx-2 h-4 data-vertical:self-auto"
        />
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2 md:flex-nowrap">
          <h1 className="truncate text-base font-medium">Guest Review Intelligence</h1>
          <Badge variant="outline" className="shrink-0 text-[11px]">
            {scopeLabel}
          </Badge>
          <Badge variant={canManageTickets ? "secondary" : "outline"} className="shrink-0 text-[11px]">
            {workflowLabel}
          </Badge>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2 md:flex-nowrap">
          <Select
            value={activeRoleCode}
            onValueChange={(value) => {
              if (value) setActiveRoleCode(value)
            }}
            disabled={isLoading || roles.length === 0}
          >
            <SelectTrigger className="h-8 w-[220px] text-xs">
              <SelectValue placeholder={isLoading ? "Loading roles…" : "Select demo role"}>
                {(value) => roleLabels[value] ?? value}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {roles.map((role) => (
                <SelectItem key={role.code} value={role.code}>
                  {role.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {activeRole?.code === "department_head" && (
            <Select
              value={assignedDepartmentCode}
              onValueChange={(value) => {
                if (value) setAssignedDepartmentCode(value)
              }}
              disabled={departments.length === 0}
            >
              <SelectTrigger className="h-8 w-[200px] text-xs">
                <SelectValue placeholder="Assign department">
                  {(value) => departmentLabels[value] ?? value}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {departments.map((department) => (
                  <SelectItem key={department.code} value={department.code}>
                    {department.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      </div>
    </header>
  )
}
