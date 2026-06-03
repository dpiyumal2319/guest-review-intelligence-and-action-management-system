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

  return (
    <header className="flex h-(--header-height) shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-(--header-height)">
      <div className="flex w-full flex-wrap items-center gap-3 px-4 py-2 lg:gap-4 lg:px-6">
        <SidebarTrigger className="-ml-1" />
        <Separator
          orientation="vertical"
          className="mx-2 h-4 data-vertical:self-auto"
        />
        <div className="min-w-0 flex-1">
          <h1 className="text-base font-medium">Guest Review Intelligence</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="text-[11px]">
              {scopeLabel}
            </Badge>
            <Badge variant={canManageTickets ? "secondary" : "outline"} className="text-[11px]">
              {workflowLabel}
            </Badge>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={activeRoleCode || undefined}
            onValueChange={(value) => {
              if (value) setActiveRoleCode(value)
            }}
            disabled={isLoading || roles.length === 0}
          >
            <SelectTrigger className="h-8 w-[220px] text-xs">
              <SelectValue placeholder={isLoading ? "Loading roles…" : "Select demo role"} />
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
              value={assignedDepartmentCode || undefined}
              onValueChange={(value) => {
                if (value) setAssignedDepartmentCode(value)
              }}
              disabled={departments.length === 0}
            >
              <SelectTrigger className="h-8 w-[200px] text-xs">
                <SelectValue placeholder="Assign department" />
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
