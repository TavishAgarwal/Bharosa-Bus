# Web test report

Scope: the static site in `web/` (index.html, routes.html, operators.html) served over http on localhost. Nothing was hosted and no demo video was made.

## What was tested and the result

| Area | Method | Result |
|---|---|---|
| Data integrity | JSON checks on 32 queries, 159 options, 40 routes, 60 operator rows | No empty queries, valid crowding levels, no markup characters in strings. Now automated in `tests/test_web_data.py`. |
| HTTP | Requests for each page and data file | All return 200; a nonexistent path returns 404. |
| index.html | Every trip and time combination (96 runs in the first pass, 32 after the escape change), real input events | 0 JS errors, 0 empty results, option order matches the score formula, the comfort slider changed the first option in 20 of 32 queries, all network requests 200. |
| routes.html | 400 route, day and band combinations | All render. |
| operators.html | 18 filter combinations | All render. |
| Mobile 375x812 | Horizontal overflow and font size | index.html and routes.html fit. Minimum font 13.1 px on index. **operators.html overflowed (613 px).** |
| Accessibility (index) | Script checks | lang, title, viewport, one h1, no duplicate ids, all 3 controls labelled. White text on the chip colours: seats 5.08, crowded 5.62, standing 3.64, unknown 3.45 (the last two are below the 4.5:1 AA level for small text). No `main` landmark, no aria-live region for results. |

## Defects found and fixed

1. operators.html overflowed on a phone. The table now sits in a scrollable wrapper (page width 375 after the fix, 60 rows still render).
2. Values from the JSON were put into innerHTML unescaped. An `esc()` helper now covers route, stop, time and stretch names on index.html and operators.html. The data holds no "<" today, so this was a hardening change, not a live bug.
3. The load-failure message said "Run `make export` first", which is wrong when the real cause is opening the file directly. All three pages now say to serve the folder over http and to run `make export` only if the data is missing.

4. Chip contrast: "standing" chip darkened to #8a5a00 (5.93:1 with white text) and "unknown" to #6b6b6b (5.33:1). Seats and crowded were already above 4.5:1. The route map key uses the same standing colour.
5. All three pages now wrap content in `<main>`; the results area on index.html and the table body on operators.html are `aria-live="polite"`. Checked in the browser on index.html (chip colours, landmark, live region); the other two pages were checked for the `<main>` tag only.

## Not fixed or not verified

- The file:// error message was changed in code but not checked in a browser.
- routes.html and operators.html were not tested for keyboard use or contrast.
- The "Max people/bus" column on the operators page reads "100+" in 43 of 60 rows, so it says little.
- No timing or load measurements were taken.
- Not a real-device test; the mobile check used viewport emulation.
