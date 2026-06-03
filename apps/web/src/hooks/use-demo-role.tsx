"use client"

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"

import type { DemoRole, Department } from "@/lib/api-types"

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
const ACTIVE_ROLE_STORAGE_KEY = "demo-role.active-role"
const ASSIGNED_DEPARTMENT_STORAGE_KEY = "demo-role.assigned-department"

type DemoRoleContextValue = {
  isLoading: boolean
  error: string | null
  roles: DemoRole[]
  departments: Department[]
  activeRole: DemoRole | null
  activeRoleCode: string
  assignedDepartmentCode: string
  effectiveDepartmentCode: string | null
  scopeLabel: string
  workflowLabel: string
  canManageTickets: boolean
  setActiveRoleCode: (roleCode: string) => void
  setAssignedDepartmentCode: (departmentCode: string) => void
}

const DemoRoleContext = createContext<DemoRoleContextValue | null>(null)

function preferredRoleCode(roles: DemoRole[], storedRoleCode: string | null): string {
  if (storedRoleCode && roles.some((role) => role.code === storedRoleCode)) {
    return storedRoleCode
  }
  if (roles.some((role) => role.code === "operations_manager")) {
    return "operations_manager"
  }
  return roles[0]?.code ?? ""
}

function preferredDepartmentCode(departments: Department[], storedDepartmentCode: string | null): string {
  if (storedDepartmentCode && departments.some((department) => department.code === storedDepartmentCode)) {
    return storedDepartmentCode
  }
  return departments[0]?.code ?? ""
}

function scopeLabelForRole(role: DemoRole | null, departmentName: string | null): string {
  if (!role) return "Loading demo scope"
  if (role.code === "admin") return "All departments"
  if (role.code === "operations_manager") return "All operational departments"
  if (role.code === "department_head") return departmentName ? `${departmentName} default scope` : "Assigned department scope"
  return "Cross-functional read-only view"
}

function workflowLabelForRole(role: DemoRole | null): string {
  if (!role) return "Loading workflow"
  return role.permissions.includes("tickets:manage") ? "Ticket management enabled" : "Read-only analytics workflow"
}

export function DemoRoleProvider({ children }: { children: ReactNode }) {
  const [roles, setRoles] = useState<DemoRole[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [activeRoleCode, setActiveRoleCode] = useState("")
  const [assignedDepartmentCode, setAssignedDepartmentCode] = useState("")
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function loadConfig() {
      setIsLoading(true)
      setError(null)
      try {
        const response = await fetch(`${apiBaseUrl}/config`)
        if (!response.ok) {
          throw new Error("Failed to load demo roles")
        }
        const payload = await response.json()
        if (cancelled) return

        const nextRoles: DemoRole[] = payload.demo_roles ?? []
        const nextDepartments: Department[] = payload.departments ?? []
        const storedRoleCode = typeof window === "undefined" ? null : window.localStorage.getItem(ACTIVE_ROLE_STORAGE_KEY)
        const storedDepartmentCode = typeof window === "undefined" ? null : window.localStorage.getItem(ASSIGNED_DEPARTMENT_STORAGE_KEY)

        setRoles(nextRoles)
        setDepartments(nextDepartments)
        setActiveRoleCode(preferredRoleCode(nextRoles, storedRoleCode))
        setAssignedDepartmentCode(preferredDepartmentCode(nextDepartments, storedDepartmentCode))
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load demo roles")
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }

    void loadConfig()

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!activeRoleCode || typeof window === "undefined") return
    window.localStorage.setItem(ACTIVE_ROLE_STORAGE_KEY, activeRoleCode)
  }, [activeRoleCode])

  useEffect(() => {
    if (!assignedDepartmentCode || typeof window === "undefined") return
    window.localStorage.setItem(ASSIGNED_DEPARTMENT_STORAGE_KEY, assignedDepartmentCode)
  }, [assignedDepartmentCode])

  const activeRole = useMemo(
    () => roles.find((role) => role.code === activeRoleCode) ?? null,
    [activeRoleCode, roles]
  )
  const assignedDepartment = useMemo(
    () => departments.find((department) => department.code === assignedDepartmentCode) ?? null,
    [assignedDepartmentCode, departments]
  )
  const effectiveDepartmentCode = activeRole?.code === "department_head" ? assignedDepartmentCode || null : null
  const scopeLabel = scopeLabelForRole(activeRole, assignedDepartment?.name ?? null)
  const workflowLabel = workflowLabelForRole(activeRole)
  const canManageTickets = activeRole?.permissions.includes("tickets:manage") ?? false

  const value = useMemo<DemoRoleContextValue>(() => ({
    isLoading,
    error,
    roles,
    departments,
    activeRole,
    activeRoleCode,
    assignedDepartmentCode,
    effectiveDepartmentCode,
    scopeLabel,
    workflowLabel,
    canManageTickets,
    setActiveRoleCode,
    setAssignedDepartmentCode,
  }), [
    activeRole,
    activeRoleCode,
    assignedDepartmentCode,
    canManageTickets,
    departments,
    effectiveDepartmentCode,
    error,
    isLoading,
    roles,
    scopeLabel,
    workflowLabel,
  ])

  return <DemoRoleContext.Provider value={value}>{children}</DemoRoleContext.Provider>
}

export function useDemoRole() {
  const context = useContext(DemoRoleContext)
  if (context === null) {
    throw new Error("useDemoRole must be used within DemoRoleProvider")
  }
  return context
}
