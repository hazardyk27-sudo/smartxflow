"""Real Chromium viewport smoke for Analizler V4; no live Supabase or user data."""
from __future__ import annotations

import re
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
VIEWPORTS = [
    ("desktop", 1440, 900, 3),
    ("tablet", 800, 1024, 2),
    ("phone", 390, 844, 1),
    ("compact_phone", 320, 568, 1),
    ("landscape", 844, 390, 2),
]

def fixture(day: str, kickoff: str, motor: str, label: str, uid: str):
    return {
        "id": 11 if motor.endswith("V1") else 22,
        "engine": motor,
        "uid": uid,
        "day": day,
        "kickoff_utc": kickoff,
        "home": label,
        "away": "Deplasman",
        "league": "Süper Lig",
        "market": "1X2",
        "selection": "1",
        "odds": 1.85,
        "kind": "EARLY_SIGNAL",
        "stage_status": "AS_RECORDED",
        "checkpoint": 8,
        "source_checkpoint": 8,
        "observed_at": kickoff,
        "selection_status": "ELIGIBLE",
        "review_state": "VALID_PREMATCH_RECORD",
        "ruleset_status": "CURRENT",
    }

def main():
    html = (ROOT / "templates/index.html").read_text(encoding="utf8")
    start = html.index('<div id="sxfBaseSignalOverlay"')
    stop = html.index('    <div class="mf-overlay"', start)
    modal = html[start:stop]
    style = (ROOT / "static/css/style.css").read_text(encoding="utf8")
    v4css = (ROOT / "static/css/base-signals.css").read_text(encoding="utf8")
    js = (ROOT / "static/js/base-signals.js").read_text(encoding="utf8")
    document = "<!doctype html><html lang='tr'><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>" + style + "</style><style>" + v4css + "</style></head><body>" + modal + "</body></html>"
    tr_now = datetime.now(ZoneInfo("Europe/Istanbul"))
    day = tr_now.date().isoformat()
    kickoff = datetime.combine(tr_now.date(), time(18, 0), ZoneInfo("Europe/Istanbul")).astimezone(timezone.utc).isoformat()
    payload = {
        "status": "ok", "phase": "SHADOW", "ruleset_mode": "CURRENT", "engines": [
            "EARLY_MONEY_CORE", "EARLY_MONEY_T12", "1X2_CONCENTRATION_V1",
            "1X2_CONCENTRATION_V2", "HEAVY_1X2_CONCENTRATION", "SURPRISE_TEAM",
            "STABLE_OVER_2_5", "PREMIUM_OVER_2_5",
            "PREMIUM_OVER_MIN1_70", "BTTS_YES"
        ],
        "items": [
            fixture(day, kickoff, "1X2_CONCENTRATION_V1", "Takım V1", "uid-v1"),
            fixture(day, kickoff, "1X2_CONCENTRATION_V2", "Takım V2", "uid-v2"),
            fixture(day, kickoff, "1X2_CONCENTRATION_V2", "Takım V1", "uid-v1"),
            fixture(day, kickoff, "HEAVY_1X2_CONCENTRATION", "Takım V1", "uid-v1"),
            fixture(day, kickoff, "EARLY_MONEY_CORE", "Takım V1", "uid-v1"),
        ],
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for name, width, height, expected_columns in VIEWPORTS:
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
            # Keep the document on a stable same-origin test URL, not about:blank.
            page.route("https://sxf-preview.test/", lambda route: route.fulfill(status=200, body="<html></html>"))
            page.route("**/api/base-signals/feed*", lambda route: route.fulfill(status=200, json=payload))
            page.goto("https://sxf-preview.test/", wait_until="load")
            page.set_content(document, wait_until="load")
            page.add_script_tag(content=js)
            page.evaluate("window.openBaseSignalsPanel()")
            page.locator(".sxf-engine-tile").first.wait_for()
            page.wait_for_function("document.querySelectorAll('.sxf-engine-tile').length === 11")
            metrics = page.evaluate("""() => {
              const overlay=document.getElementById('sxfBaseSignalOverlay');
              const modal=overlay.querySelector('.sxf-panel');
              const grid=overlay.querySelector('.sxf-engine-grid');
              const first=grid.querySelector('.sxf-engine-tile');
              const rect=modal.getBoundingClientRect();
              return {
                viewport:window.innerWidth,
                scroll:document.documentElement.scrollWidth,
                panelLeft:rect.left,panelRight:rect.right,
                panelTop:rect.top,panelBottom:rect.bottom,
                columns:getComputedStyle(grid).gridTemplateColumns.split(/\\s+/).length,
                tileWidth:first.getBoundingClientRect().width,
                scrollArea:getComputedStyle(overlay.querySelector('.sxf-signal-scroll')).overflowY
              };
            }""")
            assert metrics["columns"] == expected_columns, (name, metrics)
            assert metrics["scroll"] <= width + 1, (name, "horizontal document overflow", metrics)
            assert metrics["panelLeft"] >= -1 and metrics["panelRight"] <= width + 1, (name, metrics)
            assert metrics["panelTop"] >= -1 and metrics["panelBottom"] <= height + 1, (name, metrics)
            assert metrics["tileWidth"] >= 175, (name, "unreadably narrow motor tile", metrics)
            assert metrics["scrollArea"] == "auto", (name, metrics)
            assert page.locator('.sxf-signal-date-rail').count() == 1
            assert page.locator('[data-motor="PREMIUM_OVER_MIN1_70"]').count() == 1
            assert page.locator('[data-motor="HEAVY_1X2_CONCENTRATION"]').count() == 1
            out = Path("artifacts")
            out.mkdir(exist_ok=True)
            page.screenshot(path=str(out / f"analizler-v4-{name}.png"), full_page=True)
            page.locator('[data-motor="1X2_CONCENTRATION_V1"]').click()
            details = page.locator("#sxfSignalContent").inner_text()
            assert "Takım V1" in details and "Takım V2" not in details, (name, details)
            assert page.locator("#sxfSignalContent .sxf-fixture-line").count() == 1
            assert page.locator("#sxfSignalContent .sxf-fixture-list-head").count()==1
            assert page.locator("#sxfSignalContent .sxf-signal-card").count()==0
            assert page.locator("#sxfSignalContent .sxf-list-history-group").count() == 1
            badges = page.locator("#sxfSignalContent .sxf-line-engines .sxf-direction-badge").all_inner_texts()
            assert badges == ["V1", "V2", "HEAVY", "EARLY CORE"], (name,badges)
            assert page.locator(".sxf-fixture-line").first.get_attribute("open") is None
            assert page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 1
            page.locator(".sxf-fixture-line summary").first.click()
            assert page.locator(".sxf-history-entry").count() == 4
            assert page.locator("#sxfSearchWrap").is_visible()
            page.locator("#sxfSignalBack").click()
            assert page.locator("#sxfSearchWrap").is_hidden()
            print(f"BROWSER_OK {name} {width}x{height} columns={expected_columns} panel=inside-screen no-overflow motor-isolated")
            page.close()
        browser.close()

if __name__ == "__main__":
    main()
