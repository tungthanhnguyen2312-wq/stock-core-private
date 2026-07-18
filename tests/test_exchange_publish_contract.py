import csv
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _snapshot_rows():
    with (ROOT / "screen_snapshot.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _fallback_rows():
    source = (ROOT / "data/screener_data.js").read_text(encoding="utf-8")
    match = re.search(r"window\.SCREEN_ROWS\s*=\s*(\[.*?\]);\s*window\.BREADTH_ROWS", source, re.S)
    assert match, "Không đọc được SCREEN_ROWS trong fallback"
    return json.loads(match.group(1))


class ExchangePublishContractTests(unittest.TestCase):
    def test_hpg_exchange_sentinel_is_unique_and_hose_canonical(self):
        for rows in (_snapshot_rows(), _fallback_rows()):
            hpg = [row for row in rows if row.get("ticker") == "HPG"]
            self.assertEqual(len(hpg), 1)
            self.assertEqual(hpg[0].get("exchange"), "HSX")
            self.assertNotEqual(hpg[0].get("exchange"), "HNX")

    def test_shared_frontend_exchange_display_contract(self):
        formatter = (ROOT / "assets/js/value-format.js").read_text(encoding="utf-8")
        self.assertIn('normalized === "HSX" ? "HOSE"', formatter)
        self.assertIn("displayExchange(row.exchange)", (ROOT / "app.js").read_text(encoding="utf-8"))
        self.assertIn("displayExchange(r.exchange)", (ROOT / "assets/js/company-panel.js").read_text(encoding="utf-8"))

    def test_dashboard_screener_is_full_width_without_internal_datatable_scroll(self):
        app = (ROOT / "app.js").read_text(encoding="utf-8")
        dashboard = (ROOT / "dashboard.html").read_text(encoding="utf-8")
        self.assertNotIn("scrollX:", app)
        self.assertNotIn("scrollY:", app)
        self.assertIn("dashboard-screener-card", dashboard)
        self.assertGreater(dashboard.index("dashboard-screener-card"), dashboard.index('data-resize-key="dashboard-main"'))
        self.assertIn('id="screener-cards"', dashboard)

    def test_publish_entrypoints_never_stage_everything(self):
        publisher = (ROOT / "publish_dashboard.py").read_text(encoding="utf-8")
        safe_bat = (ROOT / "sync_and_publish.bat").read_text(encoding="utf-8")
        old_bat = (ROOT / "sync_and_push.bat").read_text(encoding="utf-8")
        self.assertIn('git("add", "--", *whitelist)', publisher)
        self.assertNotIn("git add .", publisher.lower())
        self.assertNotIn("git add -a", publisher.lower())
        self.assertNotIn("git add", safe_bat.lower())
        self.assertIn("sync_and_publish.bat", old_bat)

    def test_build_manifest_public_schema_has_no_absolute_paths(self):
        manifest = json.loads((ROOT / "data/build_info.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        for key in ("build_id", "generated_at", "market_session", "git_commit", "row_counts", "files"):
            self.assertIn(key, manifest)
        serialized = json.dumps(manifest, ensure_ascii=False)
        self.assertNotIn(str(ROOT), serialized)
        self.assertNotIn("C:\\Users\\", serialized)


if __name__ == "__main__":
    unittest.main()
