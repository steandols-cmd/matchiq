"""UI-kontroll: startar backend + byggt gränssnitt, tar högupplösta skärmbilder av de fem huvudvyerna i
stående och liggande format, kontrollerar att obligatoriska element syns (V2/V3-status, källvillkor,
datatäckning, startelvans status) och jämför visuellt mot mockuperna (sida-vid-sida + mått).

    python scripts/ui_check.py --out ui-check [--data-dir DEMO] [--mockups MAPP] [--match "Bayern München"]

Utan --data-dir skapas syntetisk testdata (används i CI).
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))
os.environ.setdefault("MATCHIQ_SECRETS", "memory")

import requests  # noqa: E402
import uvicorn  # noqa: E402

from matchiq.api.app import create_app  # noqa: E402
from matchiq.core import init_app  # noqa: E402

TOKEN = "ui-check-token"
PORTRAIT = (941, 1672)
LANDSCAPE = (1672, 941)
# mockup-filnamn (som i projektet) -> (vy, orientering)
MOCKUPS = {
    "1": ("match_statistik", "portrait"), "2": ("match_djupanalys", "portrait"), "3": ("match_odds", "portrait"),
    "4": ("match_datakvalitet", "portrait"), "5": ("matchlista", "portrait"), "6": ("match_statistik", "landscape"),
    "7": ("match_djupanalys", "landscape"), "8": ("match_odds", "landscape"), "9": ("match_datakvalitet", "landscape"),
    "10": ("matchlista", "landscape"),
}
REQUIRED_TEXT = {
    "matchlista": ["Champions League", "Kommande", "Matchanalys"],
    "matchprognos": ["Hemma", "Borta", "Rättvisa odds", "BASLINJE", "Startelvor", "Förväntade hörnor", "Skott på mål"],
    "lag_spelare_startelva": ["Startelvor", "Snitt för / emot", "Identitet"],
    "datakallor_tackning": ["Källregister", "Spärrad från prognoserna", "Används i prognoserna", "Licens"],
    "utfall_kalibrering": ["walk-forward", "EXPERIMENTELL", "BASLINJE", "Frysta prognoser mot faktiskt utfall"],
    "hamta_historik": ["Driftstatus per serie och mått", "Hämta historik", "Wyscout"],
}


def seed_synthetic(data_dir: Path) -> None:
    from datetime import datetime, timedelta

    from helpers import seed_history

    from matchiq.timeutil import UTC
    app = init_app(data_dir)
    teams = seed_history(app, seasons=(2022, 2023, 2024, 2025), n_teams=16)
    now = app.clock.now()
    for i in range(0, 8, 2):
        app.repo.upsert_match(competition_code="UCL", kickoff_utc=now + timedelta(days=3, hours=i),
                              home_team_id=teams[i], away_team_id=teams[i + 1], source_id="manual",
                              status="scheduled", season_label="2026/27")
    _ = (datetime, UTC)


def start_server(data_dir: Path) -> tuple[uvicorn.Server, int]:
    from matchiq.scheduler import SchedulerThread
    app = init_app(data_dir)
    th = SchedulerThread(app, None)  # samma schemaläggare som i appen (utan nätverkssynk)
    app.extras["scheduler_thread"] = th
    th.start()
    time.sleep(1.0)
    asgi = create_app(app, TOKEN, web_dir=str(ROOT / "apps" / "web" / "dist"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(asgi, log_level="error", lifespan="off"))
    threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return server, port


def compare(mock_path: Path, shot_path: Path, out: Path) -> dict:
    """Sida-vid-sida-montage + två grova mått: färgpalettens likhet och layoutlikhet (nedskalad gråskala)."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    a = Image.open(mock_path).convert("RGB")
    b = Image.open(shot_path).convert("RGB")
    h = 1200
    a2 = a.resize((int(a.width * h / a.height), h))
    b2 = b.resize((int(b.width * h / b.height), h))
    m = Image.new("RGB", (a2.width + b2.width + 30, h + 50), (12, 20, 34))
    m.paste(a2, (0, 50))
    m.paste(b2, (a2.width + 30, 50))
    d = ImageDraw.Draw(m)
    try:
        f = ImageFont.truetype(str(ROOT / "backend/matchiq/assets/fonts/DejaVuSans-Bold.ttf"), 22)
    except OSError:
        f = ImageFont.load_default()
    d.text((10, 12), f"Mockup {mock_path.name}", fill=(255, 255, 255), font=f)
    d.text((a2.width + 40, 12), f"MatchIQ {shot_path.name}", fill=(51, 214, 159), font=f)
    m.save(out)

    def hist(img):
        hsv = np.asarray(img.convert("HSV").resize((160, 160))).reshape(-1, 3)
        hh, _ = np.histogramdd(hsv, bins=(12, 4, 4), range=((0, 256), (0, 256), (0, 256)))
        return hh / hh.sum()
    palette = float(np.minimum(hist(a), hist(b)).sum())
    ga = np.asarray(a.convert("L").resize((24, 40) if a.height > a.width else (40, 24)), dtype=float)
    gb = np.asarray(b.convert("L").resize(ga.shape[::-1]), dtype=float)
    ga, gb = (ga - ga.mean()) / (ga.std() + 1e-9), (gb - gb.mean()) / (gb.std() + 1e-9)
    layout = float((ga * gb).mean())
    return {"palette_similarity": round(palette, 3), "layout_correlation": round(layout, 3)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="ui-check")
    ap.add_argument("--data-dir")
    ap.add_argument("--mockups")
    ap.add_argument("--match", default=None, help="del av hemmalagets namn för matchvyn")
    ap.add_argument("--team", default=None)
    ap.add_argument("--scale", type=float, default=2.0)
    ap.add_argument("--theme", choices=["dark", "light"], default=None,
                    help="tema för skärmbilderna (standard: appens inställning); återställs efteråt")
    a = ap.parse_args()
    out = Path(a.out)
    (out / "skarmbilder").mkdir(parents=True, exist_ok=True)
    data_dir = Path(a.data_dir) if a.data_dir else Path(tempfile.mkdtemp(prefix="matchiq-ui-"))
    if not a.data_dir:
        seed_synthetic(data_dir)
    server, port = start_server(data_dir)
    base = f"http://127.0.0.1:{port}"
    s = requests.Session()
    s.trust_env = False
    s.headers["Authorization"] = f"Bearer {TOKEN}"
    previous_theme = s.get(f"{base}/api/settings").json().get("theme")
    if a.theme:
        s.put(f"{base}/api/settings", json={"theme": "light" if a.theme == "light" else "matchiq-dark"})
    sched = s.get(f"{base}/api/scheduler").json()
    upcoming = s.get(f"{base}/api/matches", params={"competition": "UCL", "from": sched["now_utc"],
                                                   "status": "scheduled", "limit": 50}).json()
    match = next((m for m in upcoming if a.match and a.match.lower() in m["home"].lower()), upcoming[0])
    team_id = match["away_team_id"] if not a.team else next(
        t["id"] for t in s.get(f"{base}/api/teams", params={"q": a.team}).json())
    views = {
        "matchlista": "#/matcher?c=UCL",
        "matchprognos": f"#/match/{match['id']}",
        "lag_spelare_startelva": f"#/lag/{team_id}",
        "datakallor_tackning": "#/data?tab=kallor",
        "utfall_kalibrering": "#/utvardering",
        # extra vyer för jämförelse mot mockuperna
        "match_statistik": f"#/match/{match['id']}?flik=statistik",
        "match_djupanalys": f"#/match/{match['id']}?flik=djupanalys",
        "match_odds": f"#/match/{match['id']}?flik=odds",
        "match_datakvalitet": f"#/match/{match['id']}?flik=datakvalitet",
        "datatackning": "#/data?tab=tackning",
        "hamta_historik": "#/data?tab=historik",
    }
    from playwright.sync_api import sync_playwright
    report: dict = {"match": f"{match['home']} – {match['away']}", "checks": {}, "comparisons": {}, "errors": []}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for orient, (w, h) in (("stående", PORTRAIT), ("liggande", LANDSCAPE)):
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=a.scale)
            page.on("pageerror", lambda e: report["errors"].append(str(e)))
            page.goto(f"{base}/?token={TOKEN}#/matcher")
            page.wait_for_timeout(800)
            for name, route in views.items():
                page.goto(f"{base}/{route}")
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(1200)
                try:  # vänta tills inga laddningsindikatorer syns (max 15 s)
                    page.wait_for_function("() => !document.body.innerText.includes('Laddar')", timeout=15000)
                except Exception:  # noqa: BLE001
                    report["errors"].append(f"{name} ({orient}): laddades inte klart inom 15 s")
                fname = out / "skarmbilder" / f"{name}_{orient}.png"
                page.screenshot(path=str(fname), full_page=False)
                if name in REQUIRED_TEXT and orient == "liggande" and name not in report["checks"]:
                    body = page.inner_text("body")
                    missing = [t for t in REQUIRED_TEXT[name] if t not in body]
                    report["checks"][name] = {"ok": not missing, "missing": missing}
                if name == "matchprognos" and orient == "liggande":
                    page.screenshot(path=str(out / "skarmbilder" / f"{name}_{orient}_hel.png"), full_page=True)
            page.close()
        browser.close()
    if a.mockups:
        mock_dir = Path(a.mockups)
        (out / "jamforelse").mkdir(exist_ok=True)
        for f in sorted(mock_dir.glob("*.png")):
            num = f.stem.rsplit("-", 1)[-1]
            if num not in MOCKUPS:
                continue
            view, orient = MOCKUPS[num]
            sv = "stående" if orient == "portrait" else "liggande"
            shot = out / "skarmbilder" / f"{view}_{sv}.png"
            if shot.exists():
                report["comparisons"][f"mockup-{num}"] = {"view": view, "orientation": sv,
                                                          **compare(f, shot, out / "jamforelse" / f"mockup-{num}_vs_{view}_{sv}.png")}
    if a.theme and previous_theme:
        s.put(f"{base}/api/settings", json={"theme": previous_theme})
    server.should_exit = True
    (out / "ui-check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    failed = [k for k, v in report["checks"].items() if not v["ok"]]
    if failed or report["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
