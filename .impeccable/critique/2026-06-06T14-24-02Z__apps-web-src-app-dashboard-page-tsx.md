---
target: apps/web/src/app/dashboard/page.tsx
total_score: 19
p0_count: 0
p1_count: 6
timestamp: 2026-06-06T14-24-02Z
slug: apps-web-src-app-dashboard-page-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 2 | Loading/error states exist, but the page does not make it clear which sections share filters or why counts differ. |
| 2 | Match System / Real World | 2 | "Guest mood mix", "Top operational categories", and "Priority review queue" do not map cleanly to hotel operations decisions. |
| 3 | User Control and Freedom | 2 | The filter bar exposes too much control for an overview and no saved/preset operational views. |
| 4 | Consistency and Standards | 2 | Shared filters are sent to endpoints with different support, so visible widgets can represent different datasets. |
| 5 | Error Prevention | 2 | The page invites users to trust a "priority" queue that is actually recency ordered. |
| 6 | Recognition Rather Than Recall | 2 | Users must infer what each metric means and whether it matters to the product goal. |
| 7 | Flexibility and Efficiency | 2 | Managers cannot quickly jump from the overview to the highest-risk evidence or recurring issue action. |
| 8 | Aesthetic and Minimalist Design | 1 | The page spends too much space on low-decision sections while forcing horizontal scrolling in the queue. |
| 9 | Error Recovery | 2 | Error copy exists but does not identify which endpoint/widget failed or how to retry. |
| 10 | Help and Documentation | 2 | Labels and descriptions explain sections loosely, but not the operational interpretation. |
| **Total** | | **19/40** | **Weak, salvageable with IA redesign** |

## Anti-Patterns Verdict

**LLM assessment:** This does not fail because of decorative AI visuals. It fails because it has generic dashboard grammar: large intro cards, KPI cards, two bar charts, pattern cards, and a wide table. The structure reads like "dashboard components were assembled" rather than "a hotel manager's next decision was designed."

**Deterministic scan:** `detect.mjs --json apps/web/src/app/dashboard/page.tsx` returned `[]`. No bundled detector findings were reported. That means the obvious code-level slop patterns are not present; the main defects are product framing, information hierarchy, label semantics, and responsive behavior.

**Visual overlays:** No reliable user-visible overlay was available in this session. Browser automation was not exposed as a first-class tool, so the critique uses source inspection plus deterministic CLI scan.

## Overall Impression

The dashboard has the right raw ingredients for the product: Reputation Risk, departments, recurring issues, review evidence, and action status. The current composition hides that strength. It makes managers parse a broad analytics page when the product goal is operational triage and corrective action.

## What's Working

- The overview is built from real product concepts: review platforms, Reputation Risk, departments, issue categories, recurring patterns, and action status.
- The page already uses the shared filter model, shadcn-style cards, badges, Recharts, and existing domain types rather than a one-off visual system.
- There is enough backend data available to build a stronger overview without inventing a new product direction.

## Priority Issues

**[P1] The overview has no clear primary job**

**Why it matters:** The page mixes executive summary, recurring issue discovery, and review queue behavior. A hotel manager cannot immediately tell whether this page is for monitoring, deciding, or acting.

**Fix:** Reframe the overview around one operational question: "What needs attention now?" Lead with risk pressure and action backlog, then show the strongest supporting evidence. Move generic platform/scope copy out of the top visual hierarchy.

**Suggested command:** `$impeccable shape apps/web/src/app/dashboard/page.tsx`

**[P1] The top cards are low-value noise**

**Why it matters:** The "Kingsbury case study" intro and "Review platforms in scope" card consume the first viewport without helping the manager decide anything. They are project context, not operational state.

**Fix:** Replace the top area with a compact command surface: current risk posture, unresolved high-risk reviews, recurring issue pressure, and overdue or unverified action work if available. Keep case-study/platform context as small metadata, not a hero block.

**Suggested command:** `$impeccable distill apps/web/src/app/dashboard/page.tsx`

**[P1] Filters are too heavy for an overview and not consistently applied**

**Why it matters:** Overview pages should offer coarse pivots, not a full data-workbench filter wall. The current shared filter hook emits search, but several overview endpoints do not accept search, so the table can disagree with other widgets.

**Fix:** Use a small set of overview-safe controls, such as time window, platform, department, and risk level. Either remove search from the overview or make every displayed dataset honor it. Consider preset chips like "High risk", "Unreviewed", and "Ticket pending" instead of exposing all filters equally.

**Suggested command:** `$impeccable clarify apps/web/src/components/dashboard-filter-bar.tsx`

**[P1] The KPI set is not interrogated against the product goal**

**Why it matters:** "Verified reviews loaded", "Average rating", and raw "Negative guest mood" are weak first-order numbers for an action-management system. They describe the dataset more than the work.

**Fix:** Replace or demote KPIs that do not drive action. Prefer metrics tied to operational decisions: high/critical unreviewed reviews, recurring issue groups without tickets, open tickets by department, verified/resolved action ratio, and risk trend if available.

**Suggested command:** `$impeccable shape apps/web/src/app/dashboard/page.tsx`

**[P2] The charts occupy too much space for weak questions**

**Why it matters:** "Guest mood mix" uses a large chart to show three values. "Top operational categories" frames complaints like a leaderboard and the x-axis truncation makes scanning worse.

**Fix:** Convert simple distributions to compact segmented summaries, ranked lists, or inline bars with exact counts. Rename "Top operational categories" to something operational, such as "Highest-pressure issue groups" or "Recurring complaints by owner", and show department ownership beside category.

**Suggested command:** `$impeccable layout apps/web/src/app/dashboard/page.tsx`

**[P1] The recurring patterns section is too textual**

**Why it matters:** It asks managers to read paragraphs before deciding if the cluster matters. That is the opposite of a good overview.

**Fix:** Present recurring patterns as action-oriented rows: issue, owner department, review count, high-risk count, latest review date, platform spread, ticket state, and a short evidence excerpt. Reserve representative text for expansion.

**Suggested command:** `$impeccable distill apps/web/src/app/dashboard/page.tsx`

**[P1] The priority queue is not a usable priority queue**

**Why it matters:** It requires horizontal scrolling and is ordered by recency, not operational urgency. The most important review evidence can be visually buried.

**Fix:** Replace the wide table with a compact queue list or priority table optimized for the dashboard: review evidence, risk, owner, age, status, and action affordance. Order by critical/high risk, unreviewed/ticket-needed status, recency, and confidence or score if available.

**Suggested command:** `$impeccable adapt apps/web/src/app/dashboard/page.tsx`

## Persona Red Flags

**General Manager:** The first viewport does not answer "where is reputation risk concentrated today?" The manager sees project framing, generic KPIs, and charts before the strongest operational signal.

**Department Manager:** Department ownership is present but not prominent enough. The manager has to scan charts, pattern cards, and a wide table to find their actionable work.

**Demo Administrator:** The page demonstrates that data exists, but it does not tell a crisp product story. In a university demo, the evaluator may read it as a generic analytics dashboard rather than an action-management prototype.

## Minor Observations

- "Guest mood" is softer than the domain language. Sentiment can stay technical; Reputation Risk should be the primary product term.
- "Top" should be avoided for complaint categories. It implies ranking success, not operational pressure.
- The large chart height is not justified by the low number of categories shown.
- Loading states are plain text; skeletons or stable placeholders would reduce layout uncertainty.
- The "Review platforms in scope" information is static and should not be a large card on an operational dashboard.

## Questions to Consider

- What is the one decision this overview should help a hotel manager make in under 10 seconds?
- Which KPIs would trigger a manager to create, inspect, or verify an action ticket?
- Should the dashboard show analytics, or should it show unresolved operational risk?
- Does every section need to survive, or should the overview become a sharper launchpad into Reviews, Issues, and Tickets?
