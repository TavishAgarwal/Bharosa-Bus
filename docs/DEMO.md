# Demo script (about 2.5 minutes) and judge Q&A

Run first: `make crowding-all && make serve`, then open http://localhost:8000. The planner has two modes at the top: **Search any stop** (blue LIVE label, needs the server) and **Sample trips** (brown SAMPLE label, saved with the site). The hosted static copy has sample trips only. Drag the line between the panel and the map to resize the panel.

| Time | Show | Say |
|---|---|---|
| 0:00 | Sample trips: Rohini Sector 22 → Nehru Place, weekday 18:00 | "Planners rank by time. We add how full each bus usually is." |
| 0:15 | The map: fastest option (121 min) has red stretches. Then "Balanced": the line turns green; card says "+4 min, less crowded than the fastest" ("Most comfortable" goes further: no crowded stretch at all, +24 min) | "Here is the crowded stretch, on the map. One tab, and four minutes buys a seat." |
| 0:30 | Switch to Anand Vihar → Connaught Place, weekday 08:30, then 18:00 | "Same trip. Into town at 8:30, every option is crowded. At 18:00, against the evening flow, one extra minute gets a seat. Time and direction matter." |
| 0:45 | Labels → हिन्दी | "Labels a commuter reads in a second, in their language." |
| 0:55 | "Search any stop" tab: type two stops not in the sample list | "Not canned: any stop to any stop, planned live on the full timetable." |
| 1:05 | Same tab: Connaught Place → Anand Vihar at 21:30, Plan | "After dark it switches to Balanced by itself and favours fewer changes, short waits and short walks: +1 min saves a 16-minute walk. Not a safety score, and the app says so." |
| 1:10 | Open "Why this estimate?" | "Each label: the busiest stretch, a range, the tickets and days behind it, and the bus size. Grey means we refuse to guess." |
| 1:30 | Operators page, top of the "+1 bus" table | "For DTC: one more bus on 188DOWN at the morning peak saves about 4,900 standing minutes a day, 2,800 even on our cautious estimate." |
| 1:50 | METHOD.md §5 tables | "Most stretches really have seats, so accuracy alone is a trap. We beat an always-seats baseline with kappa 0.71, and the estimate holds from week to week." |
| 2:10 | METHOD.md §2 | "The fare column checks our stop matching: 83% exact, 99.9% within one slab." |
| 2:25 | Close | "We show what we know, and say when we don't." |

## Judge questions
- **Only 3-4% of tickets?** We scale with a stated range (ticket share 3-4%, pass-holder uplift 1.0-1.6). The network total sits inside what published ridership implies (about 29-41 lakh a day, 2025 figures). App adoption may differ by route, so same-route comparisons (later bus, other direction) are the safest thing we show.
- **Why not a running count per bus trip?** The median bus has one e-ticket per route-hour (92% have three or fewer). Scaling one ticket up 37× is noise. We pool across buses and days of a stretch-hour, which is the same count in expectation.
- **Is bus capacity real?** Capacities come from press reports. Bus size per route is inferred: short `D…` routes are 9 m DEVI buses. There is a sensitivity table for all-9 m, all-12 m and 40 + 40.
- **How do you know it's right?** Leave-one-day-out against two baselines, split-half kappa against always-seats, week-vs-rest stability, peaks at 9 and 18, weekend at 69% of weekday, the 2 Oct dip, and fare-slab agreement for stop matching. We cannot check absolute loads without an independent count, and we say so.
- **Weekends?** Nine days. Labels are weaker (kappa 0.41-0.54), and single weekend days are not predictable better than always-seats. Published as such.
- **What if there are too few tickets?** The label becomes "Not enough data", or the route's typical level at that time (marked "route average").
