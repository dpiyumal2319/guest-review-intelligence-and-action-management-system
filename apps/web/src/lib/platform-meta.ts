export type PlatformMeta = {
  logo: string
  colorVar: string
}

const PLATFORM_META: Record<string, PlatformMeta> = {
  google_business_profile: {
    logo: "/logos/google-com-logo.png",
    colorVar: "var(--platform-google)",
  },
  booking_com: {
    logo: "/logos/booking-com-logo.png",
    colorVar: "var(--platform-booking)",
  },
  tripadvisor: {
    logo: "/logos/tripadvisor-com-logo.png",
    colorVar: "var(--platform-tripadvisor)",
  },
}

export function getPlatformMeta(code: string): PlatformMeta | undefined {
  return PLATFORM_META[code]
}
