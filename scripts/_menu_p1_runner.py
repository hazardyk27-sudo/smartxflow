from pathlib import Path

import _menu_p1_apply as patch


def patch_bootstrap_test_precise() -> None:
    path = patch.ROOT / "tests" / "test_app_bootstrap.js"
    text = path.read_text(encoding="utf-8")
    if "matchesDisplayCount: 20," not in text:
        marker = "    hasMoreMatches: false,\n    currentOffset: 0,\n    oddsTrendCache: {},\n"
        replacement = "    hasMoreMatches: false,\n    currentOffset: 0,\n    matchesDisplayCount: 20,\n    oddsTrendCache: {},\n"
        if text.count(marker) != 1:
            raise RuntimeError(f"precise bootstrap context marker count={text.count(marker)}")
        text = text.replace(marker, replacement, 1)

    text = text.replace(
        "/api/matches?market=moneyway_1x2&date_filter=today_future&bulk=1",
        "/api/matches?market=moneyway_1x2&date_filter=today_future&limit=20&offset=0",
    )
    path.write_text(text, encoding="utf-8")


patch.patch_bootstrap_test = patch_bootstrap_test_precise
patch.main()
