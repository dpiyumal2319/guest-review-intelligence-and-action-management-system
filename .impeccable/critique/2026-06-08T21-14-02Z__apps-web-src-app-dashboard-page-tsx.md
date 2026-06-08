---
target: apps/web/src/app/dashboard/page.tsx
total_score: 23
p0_count: 0
p1_count: 3
timestamp: 2026-06-08T21-14-02Z
slug: apps-web-src-app-dashboard-page-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 2 | Text "Loading dashboard..." instead of skeletons; no partial-load state when one fetch fails |
| 2 | Match System / Real World | 3 | Good hotel-ops vocabulary; "Avg Risk Score" lacks a 0-100 context hint |
| 3 | User Control and Freedom | 2 | Some drill-through exists (Owner Pressure → issues by dept) but Platform Risk, Recent Issues, and KPI cards are dead ends |
| 4 | Consistency and Standards | 3 | `secondary` (gray) badge used for both "active" status and "high" priority — indistinguishable from each other and from muted neutrals |
| 5 | Error Prevention | 2 | Read-only surface; API error caught but no retry action |
| 6 | Recognition Rather Than Recall | 3 | Department names and platform logos resolved; minor: risk badge variant `secondary` gray doesn't signal "high" risk |
| 7 | Flexibility and Efficiency | 2 | No keyboard shortcuts; drill-through incomplete means power users must manually navigate after seeing a signal |
| 8 | Aesthetic and Minimalist Design | 3 | Clean layout with good density; `action_leakage` and `aging_risk` data available from API but completely absent from UI |
| 9 | Error Recovery | 2 | Error message shown but generic; no retry; partial data (kpis loaded, analytics failed) shows blank analytics section with no explanation |
| 10 | Help and Documentation | 1 | No tooltips, no contextual help; "Avg Risk Score" unexplained; "Owner Pressure" undefined; "Untracked Risk" concept absent |
| **Total** | | **23/40** | **Acceptable — significant improvements needed** |

## Anti-Patterns Verdict

**LLM assessment**: No AI slop detected. The dashboard avoids gradient text, side-stripe borders, hero-metric templates, and identical card grids. The component vocabulary is consistent with the Kingsbury product register. However, the passive read-only stance — all data, no paths forward — is a product register failure: this registers as an analytics toy, not an operational tool.

**Deterministic scan**: Exit 0, zero findings. No structural anti-patterns detected in `page.tsx` or `dashboard-filter-bar.tsx`.

**Visual overlays**: Browser automation unavailable; no live overlay. Falling back to static analysis.

## Overall Impression

The dashboard has solid bones and honest data. It reads clearly at a glance and avoids noise. The single biggest failure is that every widget is a dead end: you see "5 high-risk issues in Housekeeping" and there is no path forward to act. Combined with the warm-palette color regression (gray `secondary` badges disappear against Kingsbury's ivory neutrals) and the text-only loading state, the dashboard fails the product register test — an operational tool must be navigable, not just viewable.

## What's Working

1. **Consistent density and hierarchy**: Four-column KPI cards, two-column charts, Owner Pressure grid, and bottom split work together without visual noise.
2. **Platform logos and resolved names**: Department and source names are resolved to human-readable strings; platform logos aid instant recognition.
3. **Filter state in URL**: Bookmarkable, shareable filters are the right architecture for a hotel ops demo.

## Priority Issues

**[P1] Drill-through wiring absent or incomplete**
Why it matters: The entire point of showing "3 high-risk Platform X reviews" is to let a manager investigate. Without a click path, the dashboard is a static summary, not an operational tool.
Fix: Wire `drill_through` objects from `DashboardOwnerPressureItem.issues_drill_through`, `DashboardOwnerPressureItem.reviews_drill_through`, `DashboardPlatformRiskItem.drill_through`, `DashboardIssueItem.issues_drill_through`, and KPI card `analytics.active_issues.drill_through` / `analytics.high_risk_issues.drill_through` using `useRouter().push(path?params)`.
Suggested command: /impeccable clarify

**[P1] Loading state is text, not skeleton**
Why it matters: The product register explicitly requires skeleton states for loading. Text "Loading dashboard..." gives no shape expectation and creates layout shift when content arrives.
Fix: Replace with `DashboardSkeleton` component matching the actual card grid: 4-5 KPI skeletons + 2 chart skeletons.
Suggested command: /impeccable polish

**[P1] Color semantics break against Kingsbury warm palette**
Why it matters: The `secondary` variant (shadcn gray) is used for both "active" status badges and "high" priority badges. Against warm charcoal/ivory neutrals they read as the same neutral gray — neither signals urgency. A manager looking at Priority Distribution cannot distinguish "high" from "medium" at a glance.
Fix: Use explicit amber styling (`border-amber-500 text-amber-700 bg-amber-50`) for high priority and high risk (50–74) badges.
Suggested command: /impeccable colorize

**[P2] `action_leakage` data available but not surfaced**
Why it matters: High-risk reviews with no linked issue are the operational gap this system is designed to close. Not showing this metric means the dashboard undersells its own intelligence.
Fix: Add "Untracked Risk" as 5th KPI card sourced from `analytics.action_leakage.review_count`; show as positive signal when 0.
Suggested command: /impeccable shape

**[P2] Retry missing on API failure**
Why it matters: A blank dashboard with a text error and no recovery path will fail in a live university demo.
Fix: Add a retry button on the error state that calls `loadData()`.
Suggested command: /impeccable harden

## Persona Red Flags

**Alex (Power User)**: Sees "3 high-risk platform reviews" and instinctively clicks the row. Nothing happens. Tries the badge, the platform logo, the card itself. All dead ends. Alex will bookmark the Reviews page directly and stop using the dashboard.

**Sam (Accessibility-Dependent User)**: The Owner Pressure section wraps a `<Link>` around a `<Badge>` but the link has no accessible label beyond the badge text ("2 active"). "2 active" read by a screen reader has no context about which department or what action is taken. The high-risk badge has no link wrapper at all, so it appears as a static number with no affordance.

**Riley (Stress Tester)**: Sets filters that produce zero reviews. `Department Issues` shows nothing (no empty state message). `Priority Distribution` shows nothing. `Owner Pressure` renders an empty grid. No "no data for this period" messaging anywhere. The page looks broken, not intentionally empty.

## Minor Observations

- `{">="} 50` in the High Risk Issues card should be `≥ 50` (Unicode, no JSX expression needed)
- Demo role badges (`activeRole.name`, `scopeLabel`) render as a separate row below the subtitle, adding visual weight that distracts from the header; inline them with the subtitle
- Department Issues and Priority Distribution are side-by-side but the cards don't enforce equal height; when one has 6 items and the other has 4, the grid looks misaligned
- No `tabular-nums` on count displays; numbers shift width as they change
- Nested `<Card>` inside `<CardContent>` in Owner Pressure section is a general anti-pattern but was already present

## Questions to Consider

- "What does a hotel manager's first action look like after loading this dashboard — and does every metric on screen have an obvious next step?"
- "If `aging_risk` is always 0 server-side, should the threshold_days and logic be removed from the API response to stop surfacing phantom fields?"
- "Should 'Avg Risk Score' be replaced with a more decision-driving metric like the highest single department risk or the fastest-rising issue?"
