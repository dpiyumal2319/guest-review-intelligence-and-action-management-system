"use client"

import type { ReactNode } from "react"

import { DemoRoleProvider } from "@/hooks/use-demo-role"

export function AppProviders({ children }: { children: ReactNode }) {
  return <DemoRoleProvider>{children}</DemoRoleProvider>
}
