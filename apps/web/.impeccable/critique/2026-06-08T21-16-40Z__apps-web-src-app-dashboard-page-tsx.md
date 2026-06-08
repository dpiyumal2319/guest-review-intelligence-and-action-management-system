---
target: apps/web/src/app/dashboard/page.tsx
total_score: 28
p0_count: 0
p1_count: 0
timestamp: 2026-06-08T21-16-40Z
slug: apps-web-src-app-dashboard-page-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Skeleton grid matches real layout; retry on error; still no per-widget reload |
| 2 | Match System / Real World | 3 | "0–100 across reviews" added to Avg Risk Score; hotel-ops vocabulary intact |
| 3 | User Control and Freedom | 3 | All drill-through paths wired: KPI cards, Owner Pressure (both badges), Platform Risk rows, Recent Issue titles |
| 4 | Consistency and Standards | 4 | Amber badge semantics for high/urgent now distinguish from gray neutral; `tabular-nums` on all counts |
| 5 | Error Prevention | 2 | Read-only surface; errors caught; no destructive actions possible |
| 6 | Recognition Rather Than Recall | 3 | All drill-through targets are labeled buttons; hover affordance on Platform Risk rows |
| 7 | Flexibility and Efficiency | 3 | Every metric on screen now has an explicit navigation path; power users can go straight from KPI to filtered list |
| 8 | Aesthetic and Minimalist Design | 3 | Untracked Risk surfaced; equal-height chart cards; role badges inlined; empty states on all sections |
| 9 | Error Recovery | 3 | Styled error container; retry button calls loadData(); partial-load scenario still shows blank analytics section |
| 10 | Help and Documentation | 1 | No tooltips; "Owner Pressure", "Untracked Risk" still undefined in the UI |
| **Total** | | **28/40** | **Good — address weak areas, solid foundation** |

## Anti-Patterns Verdict

**LLM assessment**: No AI slop. Clean product-register dashboard. No gradient text, no identical card grids, no hero-metric template. The Kingsbury palette now has semantically correct severity signal colors: amber for high risk/priority reads distinctly against warm neutrals, red destructive for critical/urgent, gray secondary for neutral active states.

**Deterministic scan**: Exit 0 on updated file. Zero findings.

## Overall Impression

The rework closes the three major regressions from the theme/analytics changes. The drill-through wiring turns a passive summary into a navigable operational tool. The Untracked Risk card surfaces the most actionable gap the system can detect. The remaining ceiling is the help/documentation score — no tooltips or contextual definitions — but that is appropriate to defer for a demo-ready prototype.

## What's Working

1. **Complete drill-through coverage**: Every number on the dashboard now has a forward path. Owner Pressure department cards, Platform Risk rows, Recent Issues titles, and KPI cards all navigate to filtered lists.
2. **Semantic severity colors**: Amber badges for high risk (50–74) and high priority are now visually distinct from gray secondary (medium/active) and red destructive (urgent/critical), directly addressing the Kingsbury palette regression.
3. **Skeleton loading with structural fidelity**: The skeleton matches the actual card grid (5 KPI cards + 2 chart cards), preventing layout shift and setting correct spatial expectations.

## Priority Issues

**[P2] Partial-load blank section**
Why it matters: If `action-analytics` request fails while `kpis` succeeds, the lower half of the dashboard disappears with no message.
Fix: Guard the `{analytics && ...}` blocks with an explicit analytics error state showing "Analytics unavailable — retry."
Suggested command: /impeccable harden

**[P2] Help and Documentation remains absent**
Why it matters: "Owner Pressure", "Untracked Risk", and the 0–100 risk scale are undefined for first-time demo stakeholders.
Fix: Add `title` attributes or shadcn Tooltip wrappers on card headings and metric labels.
Suggested command: /impeccable clarify

**[P3] Recent Issues title truncation is fixed-width**
Why it matters: `max-w-[200px]` is a magic number that does not respond to the card's actual width.
Fix: Use `flex-1 truncate` on the text container instead of a fixed max-width.
Suggested command: /impeccable polish

## Minor Observations

- The 5th KPI card (Untracked Risk) renders `col-span-2 md:col-span-1` behavior naturally via the xl:grid-cols-5 grid — it fills half a row on md and a full slot at xl, which is acceptable.
- The nested Card pattern in Owner Pressure remains; noted for a future distill pass.
- `tabular-nums` added to all count displays prevents number jitter on filter change.

## Questions to Consider

- "Should the Untracked Risk card link text read 'View X reviews' on hover to communicate where clicking goes?"
- "Is 'Owner Pressure' the right label for a hotel GM — would 'Department Load' be more immediately clear?"
