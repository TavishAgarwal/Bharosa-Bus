// The narration, one entry per beat. `say` = what the voice reads; `cap` = on-screen caption (defaults to say).
// Demo beats: the matching actions in the live app are in scripts/record.mjs. `hold` adds seconds after the line.
export const VOICE = "Aman (English (India))";
export const RATE = 172;
export const beats = [
  // ---------- 1. Opening hook (~15 s) ----------
  {id: "h1", section: "hook", say: "Every evening, lakhs of people in Delhi wait for a bus. Every app tells them when it will come."},
  {id: "h2", section: "hook", say: "None of them tells you whether you will get a seat, have to stand, or spend an hour squeezed in the aisle."},
  // ---------- 2. Solution overview (~30 s) ----------
  {id: "s1", section: "solution", say: "Bharosa Bus, bharosa means trust, estimates how full each Delhi bus usually is, stretch by stretch, from 2.56 million October e-tickets and the city's G T F S timetable.",
   cap: "Bharosa Bus (bharosa = trust) estimates how full each Delhi bus usually is, stretch by stretch, from 2.56 million October e-tickets and the city's GTFS timetable."},
  {id: "s2", section: "solution", say: "Each ticket is matched to its boarding and alighting stops. We count people on board for every stretch, by route, direction and hour, and scale up with stated ranges."},
  {id: "s3", section: "solution", say: "And it earns trust: a range on every number, a not enough data state instead of guesses, bus size inferred per route, and labels tested against lazy baselines.",
   cap: "And it earns trust: a range on every number, “not enough data” instead of guesses, bus size inferred per route, and labels tested against lazy baselines."},
  // ---------- 3. Prototype demo (~90 s) ----------
  {id: "d1", section: "demo", chip: "Planner", say: "A real trip: Rohini Sector 22 to Nehru Place, on a weekday at six in the evening. The fastest option takes 121 minutes, and the map shows exactly where it gets crowded."},
  {id: "d2", section: "demo", chip: "Planner", say: "Switch to Balanced. For four more minutes, the planner finds a trip where seats are likely, and says the trade-off in one line."},
  {id: "d3", section: "demo", chip: "Evidence", say: "Every label can be checked. Why this estimate shows the busiest stretch, the range, the tickets and days behind it, and the bus size. Where data is thin, it shows grey instead of guessing.",
   cap: "Every label can be checked. “Why this estimate?” shows the busiest stretch, the range, the tickets and days behind it, and the bus size. Where data is thin, it shows grey instead of guessing.", hold: 1.5},
  {id: "d4", section: "demo", chip: "Hindi", say: "Labels switch to Hindi in one tap, for the people who actually ride these buses."},
  {id: "d5", section: "demo", chip: "Direction and time", say: "Direction and time matter. Anand Vihar to Connaught Place at eight thirty in the morning: every option is crowded. At six in the evening, against the flow, one extra minute buys a seat.",
   cap: "Direction and time matter. Anand Vihar → Connaught Place at 8:30 am: every option is crowded. At 6 pm, against the flow, one extra minute buys a seat."},
  {id: "d6", section: "demo", chip: "Live search", say: "It is not limited to sample trips. In live mode, pick any two of 4,614 stops, and the planner searches the full timetable in under a second.", hold: 2},
  {id: "d6n", section: "demo", chip: "After dark", say: "After dark, the planner adjusts by itself. Connaught Place to Anand Vihar at nine thirty at night: it switches to Balanced, and puts fewer changes, short waits at stops and short walks first. One minute more saves a sixteen minute walk. It is not a safety score, and the app says so.",
   cap: "After dark, the planner adjusts by itself. Connaught Place → Anand Vihar at 9:30 pm: it switches to Balanced, and puts fewer changes, short waits at stops and short walks first. One minute more saves a 16-minute walk. It is not a safety score, and the app says so.", hold: 1.5},
  {id: "d7", section: "demo", chip: "Route map", say: "The route map shows every busy route stretch by stretch. Here is 717 A in the morning peak, the evening peak, and on a weekend.",
   cap: "The route map shows every busy route stretch by stretch. Here is 717A in the morning peak, the evening peak, and on a weekend.", hold: 1.5},
  {id: "d8", section: "demo", chip: "Operators", say: "For operators, we rank where one more bus saves the most standing time. One extra bus on route 188 at the morning peak saves about 4,900 standing minutes a day, 2,800 even on our cautious estimate.",
   cap: "For operators, we rank where one more bus saves the most standing time. One extra bus on route 188 at the morning peak saves about 4,900 standing minutes a day — 2,800 even on our cautious estimate.", hold: 1.5},
  // ---------- 4. Impact summary (~30 s) ----------
  {id: "i1", section: "impact", say: "For commuters, especially women, older riders and parents with children, a seat is the difference between an easy ride and a hard one. Now they can choose."},
  {id: "i2", section: "impact", say: "For DTC and cluster operators, an evidence-backed list of where one more bus helps the most."},
  {id: "i3", section: "impact", say: "Next: Pink Saheli card data, because women ride free and are missing from e-tickets today. Then same-day estimates from live ticket feeds, in-bus counts to calibrate, and a home inside Delhi's official transit apps."},
  {id: "e1", section: "end", say: "Bharosa Bus. Crowding you can trust.", cap: ""},
];
