"""Local server: the static web/ pages plus a live planner API, so any trip can be planned, not only demo pairs.

  GET /api/health                                   -> {"ok": true}
  GET /api/stops                                    -> list of stop names (for autocomplete)
  GET /api/plan?from=..&to=..&time=HH:MM&day=weekday -> same shape as one entry of demo_journeys.json

Run: make serve (http://localhost:8000). The static site (make site) still works without it, on demo trips only.
"""
from __future__ import annotations

import json
import re
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import config

ROOT = Path(__file__).resolve().parents[2]
NET = None


class Handler(SimpleHTTPRequestHandler):
    def _json(self, obj, code: int = 200) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        if not u.path.startswith("/api/"):
            return super().do_GET()
        from planner.csa import plan
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/api/health":
            return self._json({"ok": True})
        if u.path == "/api/stops":
            return self._json(sorted(set(NET.stop_names)))
        if u.path == "/api/plan":
            src, dst = q.get("from", "").strip()[:80], q.get("to", "").strip()[:80]
            t, day = q.get("time", "08:30"), q.get("day", "weekday")
            if not src or not dst or not re.fullmatch(r"\d{1,2}:\d{2}", t) or day not in ("weekday", "weekend"):
                return self._json({"error": "need from, to, time=HH:MM, day=weekday|weekend"}, 400)
            try:
                opts = plan(src, dst, t, day, 0.0, NET)
            except Exception as e:  # keep the demo alive on odd input
                return self._json({"error": str(e)[:200]}, 500)
            return self._json({"from": src, "to": dst, "depart": t, "day_type": day, "options": opts,
                               "from_resolved": opts[0]["from"] if opts else "", "to_resolved": opts[0]["to"] if opts else ""})
        return self._json({"error": "unknown endpoint"}, 404)


def run(port: int = 8000) -> None:
    global NET
    sys.path.insert(0, str(ROOT))
    from planner.csa import load_network
    print("loading network and crowding tables ...")
    NET = load_network(config.GTFS_DIR, config.INTERIM_DIR, config.OUT_DIR)
    srv = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(ROOT / "web")))
    print(f"http://localhost:{port}  (live planner on)")
    srv.serve_forever()


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
