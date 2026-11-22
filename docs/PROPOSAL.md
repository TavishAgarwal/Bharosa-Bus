# Bharosa Bus: proposal (Problem 2, crowdedness-aware journey planner)

**Idea.** A Delhi bus planner that shows how full each option usually is: seats, standing room or crowded, in English or Hindi. When the data is too thin, it says "not enough data" instead of guessing. Each option states its trade-off in one line ("+2 min, less crowded than the fastest"), and each label opens a card with the tickets, days, range and bus size behind it.

**How the estimate is built.** About 2.56M October 2026 e-tickets become passenger loads per stretch, hour and day part on each directional route. Each ticket adds its riders to every stretch between its boarding and alighting stops. The load per bus is divided by the larger of scheduled trips and buses seen on tickets, then scaled for the 3-4% ticket sample with stated ranges. Two corrections most pipelines miss:

- Route-name normalisation recovers 236k tickets that a plain join drops.
- A per-route factor covers tickets that can't be placed on a stretch.

Bus size is inferred per route: short `D…` routes (median 10 km) are 9 m DEVI buses with fewer seats.

**Why it is grounded.** Most stretches really do have seats, so raw accuracy flatters any model. We test against harder baselines and publish where we fail.

| Check | Result |
|---|---|
| Hide each day, predict it (day part, weekday) | Error 0.48, against 0.62 for a route × hour average and 0.77 for an hour-of-day average |
| Labels from two halves of the month (weekday) | 92.6% agree vs 85.7% for "always seats"; kappa 0.71; 83% of busy cells caught |
| Each week vs the rest of the month (weekday) | Spearman 0.87-0.89, kappa 0.61-0.67 |
| Fare slab vs distance between matched stops | 83% exact, 99.9% within one slab (checks our stop matching) |
| Known patterns | Peaks at 9:00 and 18:00, weekend at 69% of weekday, 2 Oct holiday dip |

**What commuters get.** A planner for any stop pair, plus a faster-vs-comfortable slider. Each ride shows its crowding level, falling back to the route's typical level, clearly marked, when stretch data is thin. Every option has a one-line trade-off and an evidence card. After dark the ranking adjusts by itself, putting fewer changes, short waits at stops and short walks first (it is not a safety score). There is also a route map coloured by crowding.

**What operators get.** "If you add one bus here": standing passenger-minutes saved per day, by route and day part, ranked by the cautious estimate. Example: one more bus on 188DOWN at the weekday morning peak saves about 4,900 minutes a day (2,800 at the low end).

**Honest limits.**

- Absolute loads are not checked against an independent count.
- Bus capacities come from press reports, and bus size per route is inferred. A sensitivity table covers all-9 m, all-12 m and 40 + 40.
- Women ride free (Pink Saheli card) and free rides are not in the data: all 2.56M tickets are paid, with only 8 at zero fare. Crowding is likely underestimated where women are a large share of riders. Card-tap data from DTC would fix this.
- Ticket share and pass-holder uplift are assumed ranges, and app use may differ by route. Same-route comparisons (a later bus, the other direction) are the safest thing we show.
- We don't count per bus trip: the median bus has one e-ticket per route-hour.
- Weekend labels are weak (9 days).
- Travel times are scheduled, not observed.

**Deliverables.**

- Rerunnable pipeline: `make crowding-all`, raw CSV to web data in 107 s.
- Queryable tables: `python -m bharosa.query`.
- Live demo: `make serve`. Static site: `make site`.
- 33 tests.
- Technical note: `docs/METHOD.md`.
- Backtest, fare-check, sanity and operator outputs in `data/out`.
