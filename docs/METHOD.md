# Technical note: how Bharosa Bus estimates crowding

Data: 2,559,899 October 2026 bus e-tickets (2,753,606 passengers) and the Transport Stack static GTFS (6,862 stops, 2,574 routes, 80,357 trips, `shapes.txt` present). Every number below comes from `make crowding-all` (107 s on a laptop, raw CSV to web data).

## 1. Pipeline
1. **Clean** (`clean.py`). Parse `created_at` to IST, blank/`NULL` `vehicle_number` to missing. No rows dropped: all had a valid time, count, route, stops and date in 1-31 Oct.
2. **Match stops** (`stops.py`). Ticket stop names to GTFS stops in tiers: manual bridge, exact on the ticket's own route, fuzzy on that route, exact global, fuzzy global. GTFS names are compound (`Badarpur /Jaitpur Crossing`), so each `/`-part is an alias. **90.1% of tickets match at both ends.** Unmatched names by volume: `data/out/stops_unmatched.csv`.
3. **Stretch loads** (`load.py`). Route names are directional (`717AUP` / `717ADOWN`). A route's stop order is its longest scheduled trip. A ticket boards at position i, alights at j > i, and adds its passengers to every stretch between. A stretch's hour is the ticket time plus the scheduled run time from i. Ticket route names are normalised the same way as GTFS names (`OMS(-)DOWN`, `D-034UP`); before this fix 11% of tickets were silently dropped. **2,054,668 tickets (80%) resolve to stretches.**
4. **Route facts** (`routeinfo.py`).
   - *Bus size, inferred.* DEVI mohalla buses are 9 m electric buses on short feeder routes of about 10-15 km (press reports). In this GTFS, routes named `D…` have a median length of 10.2 km against 19.1 km for the rest. Rule: `D…` and at most 20 km → 9 m (23 seats + 13 standing), else 12 m (39 + 24). 394 routes are 9 m, carrying 5.8% of ticketed passengers.
   - *Coverage correction.* Loads come from resolved tickets, but the scale-up assumes all tickets. Per route: `cov_factor = all passengers / resolved passengers`, capped at 2 (median 1.08). The point estimate and the high end use it. The low end does not.
5. **Load per bus** (`expand.py`). Passengers on a stretch in an hour, divided by the number of trips. Trips = the larger of scheduled trips leaving that stretch in that hour, and buses seen on tickets (75th percentile over days of distinct `vehicle_number`s for the route and hour; a lower bound, since half the tickets have no vehicle number). Days with no tickets count as zero. Interval: bootstrap over days of that day type (5th-95th percentile).
6. **Scale up.** `load = raw / ticket_share × pass_holder_uplift × cov_factor`, with ticket share 3-4% (event page) and uplift 1.0-1.6 (assumed). The range ends use the extreme assumptions, so the shown range is wide on purpose.
7. **Pool thin cells.** Hour cells are also pooled into five day parts (5-6, 7-10, 11-16, 17-20, 21-4). The planner uses the hour cell if it has enough tickets, else the pooled cell, and says which.
8. **Levels and abstention** (`levels.py`). `seats` if load ≤ seats, `standing` up to seats + rated standing, else `crowded`, using each route's inferred bus. A cell with fewer than 30 tickets in the month, or a suspect schedule, shows `insufficient_evidence`.
9. **Planner** (`planner/csa.py`, live via `bharosa.serve`). Connection scan over scheduled GTFS with walking transfers. Each ride shows the level of its worst stretch. When under half of a ride's stretches have evidence, it falls back to the route's typical level at that time of day (marked "route average"), else "Not enough data". Options include later departures and alternatives that avoid each used route. Score = minutes + 4 per change + 2 × comfort weight × crowd penalty (0 / 0.35 / 1.0 per ride minute for seats / standing / crowded; unknown counts as 0.35).
   - *After dark* (leaving 20:00-04:59) the planner adjusts by itself. Balanced and Most comfortable also add 6 per change (10 in all), 1.5 × minutes waiting at stops between rides and 1 × minutes walking. A search made on Fastest switches to Balanced, and the next daytime search switches back. After dark, the time spent off the bus (waiting at stops, walking to and from them, changing buses) is the part of a trip a rider cannot sit through, so it gets extra weight. All three come from the timetable. **It is not a safety score**: we have no data on lighting, policing or incidents, and the app says so. Example (weekday 21:30, Connaught Place → Anand Vihar): the fastest option includes a 20-minute walk; the after-dark ranking puts first one arriving 1 minute later with a 4-minute walk.

### Why not a running count per bus trip?
The brief suggests grouping tickets by bus trip. We measured what that would rest on: for a bus with a vehicle number, the **median is 1 e-ticket per route-hour, and 92% have 3 or fewer**. A per-trip count would scale one or two tickets up by about 37× and mostly measure sampling noise. So we pool across the buses and days of a stretch-hour, which is the same running count in expectation, and say so. For the same reason we do not show "chance of a crowded bus" from day-to-day spread: with this sample that spread is mostly sampling noise, not real variation.

## 2. Checks we added on our own inputs
**Fare check of stop matching** (`fares.py`, `data/out/fare_check.json`). The fares in the data are exactly Delhi's distance slabs less a 10% e-ticket discount (non-AC 4.5 / 9 / 13.5, AC 9 / 13.5 / 18 / 22.5). For each resolved ticket we compare the fare's slab with the slab implied by the distance between its matched stops along the route:
- **83% agree exactly and 99.9% within one slab** (2.04 M tickets).
- Agreement peaks when distance is the straight-line sum of stop-to-stop hops (fitted road factor 0.9-1.0, not assumed).
- Exact name matches agree 83.3% of the time, tickets with a fuzzy match 81.9%. Fuzzy matching costs little.
- 25 of 1,086 routes agree less than 60% of the time (`fare_check_by_route.csv`). Their stop matching is the first thing to fix.

This tests our matching and stop order, not where people really got off. The fare was computed from the stop the rider declared.

## 3. Assumptions (all stated, none validated against counts)
- **Bus size per route is inferred** from route name and length. The press capacities were reported by a search, not opened. Sensitivity (pooled cells): crowded share is 15.5% if every bus is 9 m, 3.2% if 12 m, 1.2% at 40 + 40, and **3.6% with the inferred mix** (`levels_band_sensitivity.csv`).
- **Ticket share 3-4%** comes from the event page. Cross-check: published DTC + cluster ridership is about 29-41 lakh/day (2025 figures). Our 97,630 ticketed weekday passengers are 2.4-3.4% of that, and the central scale (about 37×) sits inside the implied 29-41× range.
- The same share and uplift apply to every route. Route-level differences in app adoption are not modelled (see ledger).
- The GTFS has one service for all days, so the schedule is the same on weekdays and weekends.

### Women riding free are not in the data
Women ride DTC and cluster buses free: first on a paper pink ticket, now on the Pink Saheli card. We checked whether those rides reach this dataset. They do not:
- All 2,559,899 tickets have the same `ticket_type_id` (1), and **only 8 have a zero fare**. There is no gender or concession field.
- Published estimates put women at **25-33% of bus riders in 2020-23** (government figures cited by The Wire) and at **about half in January-June 2025** (one press report: 10.48 lakh of about 20.9 lakh daily riders). A large group of riders is therefore missing from the raw counts.

What this does to our numbers:
- If the 3-4% ticket share is measured against all bus riders, free rides included, the scale-up puts women back **on average across the network**, but spreads them in proportion to paying e-ticket riders, not where women actually ride.
- So crowding is **likely underestimated on routes and at times where women are a larger share of riders** than average, and slightly overestimated where they are a smaller share. If the share excludes free rides, every load is too low by the women's share.
- We cannot tell which routes are affected from this data, so **we do not correct for it**. We state it in the app ("How to read this" and every evidence card) instead.

Fix: Pink Saheli card taps by route, stop and hour from DTC. That would remove this bias directly, and it would also give the first stretch-by-stretch picture of where and when women ride.

## 4. Bias ledger: who is missing or over-counted
| Issue | Direction | Handling |
|---|---|---|
| Tickets are a 3-4% e-ticket sample | App/QR riders may differ by route (80% of e-tickets are on AC buses) | One global scale-up. Within-route comparisons (leave later, other day part) do not depend on it; cross-route ones do |
| Pass holders have no tickets | Undercount | Uplift range 1.0-1.6 (assumed) |
| Women ride free (paper pink ticket, then the Pink Saheli card) and free rides are not in the data | Undercounts routes and hours where many women ride; overcounts where few do | Not corrected. See "Women riding free are not in the data" in §3 |
| Declared alighting stop may differ from the real one | Blurs loads | Not corrected. The fare check confirms our reading of the declared stop, not the real one |
| 20% of tickets do not resolve to a stretch | Undercount, may not be random | Per-route coverage factor (capped at 2) on the point estimate |
| Scheduled trips undercount running buses | Overstates load per bus | Floor from buses seen on tickets. Shown hour cells over 150 people/bus: 0.5%. Cells whose low estimate exceeds 100 abstain |
| Bus size per route not in the data | Either way | Inferred (9 m DEVI vs 12 m) plus a sensitivity table |

## 5. Validation (`make backtest`)
Raw units (passengers per trip) for WAPE, so assumptions cancel. Levels use the published scale and per-route bus. Cells need 30+ training tickets.

**a. Leave one day out**: hide each day and predict it from the other days of the same type.
| Grain | Day | WAPE | Hour-of-day baseline | Route × hour baseline |
|---|---|---|---|---|
| hour | weekday | **0.64** | 0.84 | 0.73 |
| hour | weekend | **0.62** | 0.73 | 0.66 |
| day part | weekday | **0.48** | 0.77 | 0.62 |
| day part | weekend | **0.53** | 0.72 | 0.61 |

The route × hour baseline knows the route and hour but not the stretch. Beating it shows the stretch-level detail carries signal.

**b. Are the labels better than "always seats"?** A single held-out day has only a few tickets per cell, so day-level labels are noisy. The fair test of a "typical day" label is **split half**: label each cell from the first half of the month and again from the second, then compare. We report agreement beyond chance (Cohen's kappa), not just raw agreement, because most cells really are "seats".
| Grain | Day | Agreement | Always-seats | Kappa | Busy cells caught (standing or crowded) | Crowded caught |
|---|---|---|---|---|---|---|
| day part | weekday | **92.6%** | 85.7% | **0.71** | 83% | 77% |
| day part | weekend | 89.6% | 85.1% | 0.54 | 55% | 48% |
| hour | weekday | 77.4% | 64.5% | 0.57 | 80% | 72% |
| hour | weekend | 64.9% | 50.7% | 0.41 | 65% | 48% |

On single held-out days, weekday kappa is 0.36 (hour; 66.5% agreement against 65.7% always-seats) and 0.50 (day part; 85.9% against 82.8%). On weekends, single-day agreement is *below* always-seats at both grains (hour 54.7% against 59.5%, day part 82.5% against 83.6%; kappa 0.25 and 0.34). We publish that rather than hide it: one weekend day is too few tickets to judge, and weekend labels are the weakest thing we show.

**c. Week to week** (the brief asks for this): each ISO week against the rest of the month, same cells.
| Grain | Weekday Spearman | Weekday kappa | Weekend Spearman | Weekend kappa |
|---|---|---|---|---|
| day part | 0.87-0.89 | 0.61-0.67 | 0.61-0.84 | 0.46-0.55 |
| hour | 0.78-0.81 | 0.50-0.53 | 0.45-0.68 | 0.31-0.41 |

No week drifts away from the others. The 2 Oct holiday week is too short to score on weekdays.

**d. Known patterns** (`make sanity`): weekday peaks at 9:00 and 18:00, about 4.2× midday. Weekend days carry 69% of a weekday's passengers. 2 Oct (Gandhi Jayanti) is among the three lowest days. Weekday day-part medians: 22 people per bus at the am peak (90th percentile 55) against 10 at midday. 7.1% of am-peak cells are crowded against 0.3% at midday.

**What this does not prove.** All of these are reliability checks: the estimate agrees with itself across days and weeks and follows known patterns. None checks absolute loads against an independent count (APC, manual counts or GPS dwell). That is the biggest open gap.

## 6. Where estimates are least reliable
- **Weekends** (9 days; split-half kappa 0.41-0.54) and low-volume routes (weekday WAPE 0.64 day part / 0.75 hour, against 0.36 / 0.52 on high-volume routes).
- **Hour cells**: 84% abstain (the rest carry 69% of passenger load). Day-part cells: 67% abstain, the rest carry 89%. 62% of shown day-part cells keep one level across their whole range. In the demo trips, 86% of ride time has a crowding estimate.
- **Absolute loads**: 3% of shown hour cells exceed 100 people per bus. Relative patterns (which stretch, which hour, which direction) hold up better than counts.
- **Cross-route comparisons** where app adoption differs. Same-route comparisons (leave 20 min later, other direction) are safer.
- **9 m inference** is a name-and-length rule. If a `D…` route runs 12 m buses, its levels are too pessimistic.
- Anything beyond October: no festivals, monsoon or seasons.

## 7. For operators: where one more bus helps most (`extra_bus_benefit.csv`)
For each route, day part and day type: standing passenger-minutes per day = Σ over stretches of max(load − seats, 0) × buses × stretch minutes. One extra bus spreads the same riders over buses + 1. We rank by the saving at the **low** end of the load range, so the top rows hold up even if our scale-up is too high. Example, weekday am peak: one more bus on 188DOWN (10 buses now) saves about 4,900 standing passenger-minutes per day (2,800 on the cautious estimate).

## 8. Not done
- Independent check of absolute loads (APC, manual counts, GPS dwell; GPS is not in the Problem 2 brief and is 16 GB).
- Observed travel times: planner times are scheduled.
- Route-level app-adoption correction (would need ETM totals per route).
