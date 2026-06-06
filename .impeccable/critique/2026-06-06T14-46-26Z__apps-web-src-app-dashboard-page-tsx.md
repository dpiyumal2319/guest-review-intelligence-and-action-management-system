---
target: apps/web/src/app/dashboard/page.tsx
total_score: 28
p0_count: 0
p1_count: 2
timestamp: 2026-06-06T14-46-26Z
slug: apps-web-src-app-dashboard-page-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Counts and priority framing are clearer, but widget-level destinations are not visible. |
| 2 | Match System / Real World | 3 | The page now speaks in operational pressure and risk, but some analytics remain passive summaries. |
| 3 | User Control and Freedom | 3 | Filters are reduced, but widgets do not offer direct drill-through actions. |
| 4 | Consistency and Standards | 3 | Overview structure is more coherent; navigation affordances are missing from repeated signal blocks. |
| 5 | Error Prevention | 3 | Queue now requests operational priority, reducing misleading ordering risk. |
| 6 | Recognition Rather Than Recall | 3 | Labels are clearer, but users must remember where to go for full reviews, issues, and tickets. |
| 7 | Flexibility and Efficiency | 2 | The dashboard surfaces work but does not let users move quickly to the corresponding work page. |
| 8 | Aesthetic and Minimalist Design | 3 | Much less noise than before, with one notable empty-space imbalance in the Risk mix card. |
| 9 | Error Recovery | 2 | Error state is still page-level and generic. |
| 10 | Help and Documentation | 3 | Copy is more operational, but action meaning is not reinforced by links/buttons. |
| **Total** | | **28/40** | **Substantially improved, still too passive** |

## Anti-Patterns Verdict

**LLM assessment:** The dashboard no longer reads like generic analytics assembly. It now has a clear "what needs attention now" frame, compact urgency metrics, owner pressure, recurring issue actions, and a priority review queue. The remaining issue is not visual slop; it is passive interactivity. The dashboard presents evidence but does not consistently let the user continue the workflow from the evidence.

**Deterministic scan:** `detect.mjs --json apps/web/src/app/dashboard/page.tsx` returned `[]`. No bundled detector findings were reported.

**Visual overlays:** No reliable user-visible overlay was available in this session. Browser automation was not exposed as a first-class tool, so the critique uses source inspection plus deterministic CLI scan.

## Overall Impression

This is a real improvement over the previous version. The page now feels like an operational dashboard rather than a generic chart wall. The next quality bar is actionability: every widget that reveals work should provide a clear route to inspect or act on that work.

## What's Working

- The page now leads with an operational question: "What needs attention now."
- The wide priority table was replaced by compact review cards that avoid horizontal scrolling.
- The backend contract now supports `order_by=operational_priority`, so the queue framing is materially more defensible.
- Platform logos are used as recognition aids rather than as a large decorative strip.
- The previous oversized bar charts are gone, replaced by compact sentiment and issue-pressure summaries.

## Priority Issues

**[P1] Widgets lack actions and drill-through routes**

**Why it matters:** The dashboard shows high-risk reviews, ticket-needed reviews, owner pressure, recurring issue actions, and priority reviews, but those blocks do not take the user to the corresponding Reviews, Issues, or Tickets page. Managers see work but must manually navigate and reconstruct the same filter context.

**Fix:** Add explicit, compact actions to each meaningful widget: view matching reviews, inspect issue group, open tickets for owner, create/inspect ticket where role allows. Preserve relevant query params when linking to `/reviews`, `/issues`, and `/tickets`.

**Suggested command:** `$impeccable clarify apps/web/src/app/dashboard/page.tsx`

**[P2] Risk mix has layout imbalance**

**Why it matters:** The Risk mix card sits beside a taller complaint-pressure card, so it leaves visual dead space below. The problem is not the data itself; the grid pairing makes the right card feel underdeveloped.

**Fix:** Either make Risk mix a compact side module that does not try to match the complaint-pressure card, or fill the vertical space with a more actionable companion signal such as risk-by-status, unresolved high-risk count, or platform risk spread.

**Suggested command:** `$impeccable layout apps/web/src/app/dashboard/page.tsx`

**[P1] Analytics are still mostly descriptive, not decision-driving**

**Why it matters:** The dashboard shows pressure and risk, but it does not yet answer enough second-order operational questions: where is risk worsening, which department is stuck, which platform is over-indexing, what is aging without action?

**Fix:** Add a small set of analytics that directly support decisions. Strong candidates: risk by platform, risk by department, action leakage, aging high-risk reviews, recurring issue without ticket, and SLA/verification backlog if ticket dates support it.

**Suggested command:** `$impeccable shape apps/web/src/app/dashboard/page.tsx`

**[P2] Recurring issue actions show ticket state but not the next move**

**Why it matters:** "Ticket needed" is visible, but there is no direct button to inspect the issue group or create a ticket. The user has to infer the workflow.

**Fix:** Add row-level actions such as "Inspect issue", "View reviews", and "Create ticket" where permissions allow. If creation is too much for the dashboard, at least link to the Issues page with matching category/department filters.

**Suggested command:** `$impeccable clarify apps/web/src/app/dashboard/page.tsx`

**[P2] Priority review cards do not expose review-level continuation**

**Why it matters:** The review card shows evidence and status, but it does not offer "View full review" or "Create ticket". That weakens the dashboard as a triage surface.

**Fix:** Add review-level actions. At minimum, link to `/reviews` with a search or review identifier filter. Better: support a review detail route or query state that opens the review in the existing review workflow.

**Suggested command:** `$impeccable adapt apps/web/src/app/dashboard/page.tsx`

## Persona Red Flags

**General Manager:** Can see high-risk pressure, but cannot click directly into the high-risk review set or department pressure set. The overview creates awareness but slows follow-through.

**Department Manager:** Owner pressure is visible, but there is no one-click path to their department's reviews, issues, or tickets from the dashboard.

**Demo Administrator:** The product story is clearer, but a live demo still needs direct "show me the evidence" links so evaluators see traceability without manual navigation.

## Minor Observations

- The Risk mix label is acceptable, but it should either be smaller or paired with another operational signal.
- The platform scope card is now small enough to tolerate.
- Compact sentiment is better than the old chart, but it should not become the dashboard's main analytic story.
- Loading states are still text-only; skeletons would reduce perceived roughness.
- The action model should respect demo role permissions already available through `useDemoRole`.

## Questions to Consider

- Should every dashboard metric be clickable, or only the ones representing unresolved work?
- Is the next step from a high-risk review to inspect evidence, create a ticket, or both?
- Which analytics would change a manager's decision today rather than just describe the dataset?
- Should the dashboard include ticket analytics, or should it stay review/issue focused and link out to Tickets?
