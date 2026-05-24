"use client"

import * as React from "react"

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
  ChartNoAxesCombinedIcon,
  CircleHelpIcon,
  ClipboardListIcon,
  LayoutDashboardIcon,
  MessageSquareTextIcon,
  RefreshCwIcon,
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
      url: "/dashboard#reviews",
      icon: <MessageSquareTextIcon />,
    },
    {
      title: "Issues",
      url: "/dashboard#issues",
      icon: <SirenIcon />,
    },
    {
      title: "Tickets",
      url: "/dashboard#tickets",
      icon: <ClipboardListIcon />,
    },
    {
      title: "Ingestion",
      url: "/dashboard#ingestion",
      icon: <RefreshCwIcon />,
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
  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              className="data-[slot=sidebar-menu-button]:p-1.5!"
              render={<a href="#" />}
            >
              <ChartNoAxesCombinedIcon className="size-5!" />
              <span className="text-base font-semibold">Hotel Review Ops</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={data.navMain} />
        <NavSecondary items={data.navSecondary} className="mt-auto" />
      </SidebarContent>
      <SidebarFooter>
        <NavUser user={data.user} />
      </SidebarFooter>
    </Sidebar>
  )
}
