---
target: apps/web/src/app/dashboard/page.tsx
total_score: 29
p0_count: 0
p1_count: 0
timestamp: 2026-06-08T21-44-59Z
slug: apps-web-src-app-dashboard-page-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Chart-shaped skeleton (donut + bar placeholders) matches real layout; retry on error |
| 2 | Match System / Real World | 3 | Semantic colors (emerald positive, amber mixed, red negative) match intuitive expectations; axis labels use resolved names |
| 3 | User Control and Freedom | 3 | All drill-through wiring preserved through chart click handlers; bar cursor="pointer" communicates affordance |
| 4 | Consistency and Standards | 4 | Unified ChartContainer + ChartTooltipContent pattern across all 6 charts; amber/red/emerald severity palette consistent throughout |
| 5 | Error Prevention | 2 | Read-only surface; no destructive actions; API errors caught with retry |
| 6 | Recognition Rather Than Recall | 4 | Donut segments color-coded and legend-labeled; bar chart Y-axes show resolved department/platform names; tooltip on hover confirms exact counts |
| 7 | Flexibility and Efficiency | 3 | Click any bar or KPI card to navigate; legend clarifies grouped bars without memorization |
| 8 | Aesthetic and Minimalist Design | 3 | Six data fields now visualized that were previously text-only; nested-Card anti-pattern in Owner Pressure eliminated; charts replace badge lists without adding noise |
| 9 | Error Recovery | 3 | Retry button + styled error container; empty-state messages on all chart sections |
| 10 | Help and Documentation | 1 | No tooltips on section headings; "Owner Pressure" and "Untracked Risk" still undefined in UI |
| **Total** | | **29/40** | **Good — approaching shippable** |

## Anti-Patterns Verdict

**LLM assessment**: No AI slop. Recharts charts use the project's own ChartContainer/ChartTooltipContent/ChartLegendContent pattern — no third-party chart library wrappers or bespoke styling. The nested-Card grid in Owner Pressure (a documented anti-pattern from the previous critique) has been replaced by a clean grouped horizontal bar chart. The donut charts use `paddingAngle={2}` and `strokeWidth={0}` for a refined gap that avoids the default harsh borders.

**Deterministic scan**: Exit 0, zero findings.

## Overall Impression

The dashboard now communicates proportional data rather than just listing counts. A manager can glance at the Sentiment Mix donut and immediately see if negative sentiment is dominant, or check the Risk Level donut to see the severity split — neither required scrolling or counting badge lines before. The grouped Owner Pressure bar makes cross-department comparison instant. The main remaining ceiling is help/documentation (no tooltips) and the partial-load blank analytics section.

## What's Working

1. **Semantic chart colors throughout**: Emerald/amber/red for sentiment, graduated amber→red for risk levels, and priority bar colors (urgent red, high amber, medium gray, low muted) all use the same color vocabulary as the Kingsbury badge palette, so there's no cognitive mismatch between charts and the rest of the UI.
2. **Drill-through preserved on charts**: Department Issues bars, Owner Pressure bars (two separate handlers for active vs high-risk), and Platform Risk bars all navigate on click with `cursor="pointer"` communicating the affordance.
3. **Structured skeleton**: Donut skeletons with hollowed center and bar-row skeletons now set accurate spatial expectations before data loads.

## Priority Issues

**[P2] Partial-load blank analytics section**
Why it matters: If `action-analytics` fails while `kpis` succeeds, the lower three sections (Owner Pressure, Platform Risk, Recent Issues) silently disappear.
Fix: Add an analytics-specific error state with retry alongside the existing global error handler.
Suggested command: /impeccable harden

**[P2] Help and documentation absent**
Why it matters: "Owner Pressure", "Untracked Risk", and the 0–100 scale remain undefined for demo stakeholders unfamiliar with the domain model.
Fix: Add `title` attributes on card headings and a one-line description in `CardDescription` for ambiguous sections.
Suggested command: /impeccable clarify

**[P3] Recent Issues title `max-w-[200px]` is a magic number**
Why it matters: Fixed pixel max-width breaks at non-standard card widths.
Fix: Replace with `flex-1 min-w-0 truncate` on the text container.
Suggested command: /impeccable polish

## Minor Observations

- `paddingAngle={2}` on donut Pie gives a clean separation without visible gaps at small segment counts
- Owner Pressure chart height scales dynamically with `Math.max(200, n * 56)` — avoids cramped bars at 6 departments
- Platform Risk Y-axis uses `width={140}` which accommodates "Google Business Profile" without wrapping
- The `BarsSkeleton` and `DonutSkeleton` helper components are purely presentational; no side effects

## Questions to Consider

- "Should the Sentiment Mix donut link to a Reviews page filtered by sentiment label?"
- "Is a 'total reviews' center label inside each donut useful, or would it add noise?"
