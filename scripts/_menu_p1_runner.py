from pathlib import Path

import _menu_p1_apply as patch


def patch_bootstrap_test_precise() -> None:
    path = patch.ROOT / "tests" / "test_app_bootstrap.js"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "/api/matches?market=moneyway_1x2&date_filter=today_future&bulk=1",
        "/api/matches?market=moneyway_1x2&date_filter=today_future&limit=20&offset=0",
    )
    path.write_text(text, encoding="utf-8")


patch.patch_bootstrap_test = patch_bootstrap_test_precise
patch.main()

# The first-paint contract is deliberately fixed at 20 rows. Keeping this URL
# independent from mutable UI state makes the critical path deterministic and
# avoids any bootstrap ordering dependency on matchesDisplayCount.
for relative in ("static/js/app.js.src", "static/js/app.js"):
    path = patch.ROOT / relative
    text = path.read_text(encoding="utf-8")
    old = "date_filter=today_future&limit=${matchesDisplayCount}&offset=0"
    count = text.count(old)
    if count < 1:
        raise RuntimeError(f"{relative}: bounded first-page token missing")
    path.write_text(text.replace(old, "date_filter=today_future&limit=20&offset=0"), encoding="utf-8")

contract = patch.ROOT / "tests" / "test_menu_first_page_contract.py"
contract_text = contract.read_text(encoding="utf-8")
contract_text = contract_text.replace(
    "date_filter=today_future&limit=${matchesDisplayCount}&offset=0",
    "date_filter=today_future&limit=20&offset=0",
)
contract.write_text(contract_text, encoding="utf-8")
