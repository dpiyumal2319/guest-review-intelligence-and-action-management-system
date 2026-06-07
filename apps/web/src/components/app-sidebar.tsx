"use client"

import * as React from "react"
import Image from "next/image"

import { useDemoRole } from "@/hooks/use-demo-role"
import { NavMain } from "@/components/nav-main"
import { NavSecondary } from "@/components/nav-secondary"
import { NavUser } from "@/components/nav-user"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import {
  CircleHelpIcon,
  LayoutDashboardIcon,
  MessageSquareTextIcon,
  SearchIcon,
  Settings2Icon,
  SirenIcon,
} from "lucide-react"

const data = {
  user: {
    name: "Demo Manager",
    email: "manager@hotel.test",
    avatar: "",
  },
  navMain: [
    {
      title: "Overview",
      url: "/dashboard",
      icon: <LayoutDashboardIcon />,
    },
    {
      title: "Reviews",
      url: "/reviews",
      icon: <MessageSquareTextIcon />,
    },
    {
      title: "Issues",
      url: "/issues",
      icon: <SirenIcon />,
    },
  ],
  navSecondary: [
    {
      title: "Settings",
      url: "#",
      icon: <Settings2Icon />,
    },
    {
      title: "Get Help",
      url: "#",
      icon: <CircleHelpIcon />,
    },
    {
      title: "Search",
      url: "#",
      icon: <SearchIcon />,
    },
  ],
}

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { activeRole, departments, assignedDepartmentCode, scopeLabel } = useDemoRole()
  const assignedDepartment = departments.find((department) => department.code === assignedDepartmentCode)
  const userName = activeRole?.code === "department_head" && assignedDepartment
    ? `${assignedDepartment.name} Lead`
    : activeRole?.name ?? data.user.name
  const userEmail = activeRole?.code === "department_head" && assignedDepartment
    ? `${assignedDepartment.code}@hotel.test`
    : activeRole?.code
      ? `${activeRole.code}@hotel.test`
      : data.user.email

  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              className="h-auto gap-2.5 py-2 data-[slot=sidebar-menu-button]:p-1.5!"
              render={<a href="/dashboard" />}
            >
              <Image
                src="/kingsbury-logo.png"
                alt="The Kingsbury crest"
                width={1344}
                height={1090}
                priority
                className="h-9 w-auto shrink-0"
              />
              <div className="flex flex-col gap-0.5 leading-none">
                <span className="text-sm font-semibold uppercase tracking-[0.18em] text-sidebar-primary">
                  The Kingsbury
                </span>
                <span className="text-[11px] tracking-wide text-muted-foreground">
                  Review Intelligence
                </span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={data.navMain} />
        <NavSecondary items={data.navSecondary} className="mt-auto" />
      </SidebarContent>
      <SidebarFooter>
        <NavUser
          user={{
            name: userName,
            email: userEmail,
            avatar: data.user.avatar,
            subtitle: scopeLabel,
          }}
        />
      </SidebarFooter>
    </Sidebar>
  )
}
