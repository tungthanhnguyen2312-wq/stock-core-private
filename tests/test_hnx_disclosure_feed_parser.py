"""hnx_disclosure_feed_parser reads candidates and structured fields from stored bytes only.

Every test fixture below reproduces the shape of a real page retained 2026-08-24 (RSS feed, an
individual registration notice, a related-person execution result with an explicit executed=0,
a major-holder-exit notice with a missing `<br/>` between its first two bullets, and an
entity-actor registration notice using HNX's own typo'd label). None of this module performs
I/O, so every test is a pure function call over inline bytes; fixtures are plain Vietnamese
text encoded to UTF-8 at the point of use, never hand-written byte escapes.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import hnx_disclosure_feed_parser as parser  # noqa: E402
import official_source_registry as registry  # noqa: E402

REG = registry.load_registry()
FEED_URL = "https://www.hnx.vn/3/vi_vn/thong-tin-cong-bo-tu-to-chuc-phat-hanh.rss"

RSS = """<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel>
<title>HNX - Thong tin cong bo</title><link>http://www.hnx.vn:7978/3/vi_vn/x.rss</link>
<item><guid isPermaLink="false">1001</guid>
<link>http://www.hnx.vn:7978/tin-cung-cap-rss-vi_vn-1001-0.html</link>
<title>Nguyễn Văn A - Tổng Giám đốc - đăng ký bán 200.000 CP</title>
<pubDate>Sat, 22 Aug 2026 15:40:00 +0700</pubDate></item>
<item><guid isPermaLink="false">1002</guid>
<link>http://www.hnx.vn:7978/tin-cung-cap-rss-vi_vn-1002-0.html</link>
<title>Nghị quyết Hội đồng quản trị</title>
<pubDate>Sat, 22 Aug 2026 15:41:00 +0700</pubDate></item>
<item><guid isPermaLink="false">1003</guid>
<link>https://evil.example.com/tin-cung-cap-rss-vi_vn-1003-0.html</link>
<title>Công ty X - đã mua 0 CP</title>
<pubDate>Sat, 22 Aug 2026 15:42:00 +0700</pubDate></item>
</channel></rss>""".encode("utf-8")

REGISTRATION_INDIVIDUAL = """<html><body>
<div class="Box-TieuDe"><label>Nguyễn Văn A - Tổng Giám đốc - đăng ký bán 200.000 CP</label></div>
<div class="Box-Thoigian"><label>15:40 22/08/2026</label></div>
<div class="Box-Tomtat"><label></label></div>
<div class="Box-Noidung">- Tên cá nhân thực hiện giao dịch: Nguyễn Văn A <br/>- Chức vụ hiện nay tại TCNY: Tổng Giám đốc<br/>- Mã chứng khoán: AIG<br/>- Số lượng cổ phiếu nắm giữ trước khi thực hiện giao dịch: 14.471.211 CP (tỷ lệ 8,48%) <br/>- Số lượng cổ phiếu đăng ký bán: 200.000 CP<br/>- Ngày dự kiến bắt đầu giao dịch: 03/09/2026<br/>- Ngày dự kiến kết thúc giao dịch: 30/09/2026.</div>
<div class="divLstFileAttach"></div></body></html>""".encode("utf-8")

# One related person, executed=0, non-execution reason -- the exact shape retained live.
EXECUTION_RESULT_ZERO = """<html><body>
<div class="Box-TieuDe"><label>Cong ty X - da mua 0 CP</label></div>
<div class="Box-Thoigian"><label>15:15 22/08/2026</label></div>
<div class="Box-Tomtat"><label></label></div>
<div class="Box-Noidung">- Tên tổ chức thực hiện giao dịch: Công ty cổ phần X <br/>- Mã chứng khoán: VNF<br/>- Số lượng cổ phiếu nắm giữ trước khi thực hiện giao dịch: 19.351.981 CP (tỷ lệ 61,05%) <br/>- Tên của người có liên quan tại TCNY: Người A <br/>- Chức vụ hiện nay của NCLQ tại tổ chức niêm yết: Ủy viên HĐQT<br/>- Chức vụ hiện nay của NCLQ tại tổ chức thực hiện giao dịch: Tổng Giám đốc<br/>- Số lượng cổ phiếu NCLQ đang nắm giữ: 30.160 CP (tỷ lệ 0,1%)<br/>- Số lượng cổ phiếu đăng ký mua: 1.000.000 CP<br/>- Số lượng cổ phiếu đã mua: 0 CP<br/>- Số lượng cổ phiếu nắm giữ sau khi thực hiện giao dịch: 19.351.981 CP (tỷ lệ 61,05%)<br/>- Lý do không thực hiện giao dịch hết số cổ phiếu đăng ký: Giá thị trường biến động chưa phù hợp<br/>- Ngày bắt đầu giao dịch: 20/07/2026<br/>- Ngày kết thúc giao dịch: 17/08/2026.</div>
<div class="divLstFileAttach"></div></body></html>""".encode("utf-8")

# Missing <br/> between the first two bullets, exactly as observed live on 2026-08-24.
MAJOR_HOLDER_GLUED = """<html><body>
<div class="Box-TieuDe"><label>Nguoi X khong con la co dong lon</label></div>
<div class="Box-Thoigian"><label>21:56 23/08/2026</label></div>
<div class="Box-Tomtat"><label></label></div>
<div class="Box-Noidung">- Tên cá nhân thực hiện giao dịch: Đỗ Đức Cường- Mã chứng khoán: VNH <br/>- Số lượng cổ phiếu nắm giữ trước khi thực hiện giao dịch: 403.000 CP (tỷ lệ 5,02%) <br/>- Số lượng cổ phiếu đã bán: 50.000 CP <br/>- Số lượng cổ phiếu nắm giữ sau khi thực hiện giao dịch: 353.000 CP (tỷ lệ 4,4%) <br/>- Ngày không còn là cổ đông lớn: 14/08/2026.</div>
<div class="divLstFileAttach"></div></body></html>""".encode("utf-8")

# HNX's registration template spells this label "giao dich" (no diacritic on the final word).
ENTITY_REGISTRATION_TYPO_LABEL = """<html><body>
<div class="Box-TieuDe"><label>Cong ty Y - dang ky mua 100.000 CP</label></div>
<div class="Box-Thoigian"><label>14:31 22/08/2026</label></div>
<div class="Box-Tomtat"><label></label></div>
<div class="Box-Noidung">- Tên tổ chức thực hiện giao dich: Công ty cổ phần Y <br/>- Mã chứng khoán: IDV <br/>- Số lượng cổ phiếu đăng ký mua: 100.000 CP.</div>
<div class="divLstFileAttach"></div></body></html>""".encode("utf-8")

# A structurally different notice family (no Box-Noidung block at all).
FUND_CERT_UNMATCHED = """<html><body>
<div class="Box-TieuDe"><label>Bao cao ket qua giao dich chung chi quy</label></div>
<div class="Box-Thoigian"><label>10:00 20/08/2026</label></div>
<div class="SomeOtherLayout">Not the bullet-list shape this parser recognises.</div>
</body></html>""".encode("utf-8")


class ParseDisclosureRss(unittest.TestCase):
    def test_classifies_and_rejects(self):
        parsed = parser.parse_disclosure_rss(RSS, feed_url=FEED_URL, source_id="hnx", registry=REG)
        self.assertEqual(parsed["item_count"], 3)
        by_guid = {row["guid"]: row for row in parsed["items"]}
        self.assertEqual(by_guid["1001"]["state"], "candidate")
        self.assertEqual(by_guid["1001"]["document_class"], parser.INSIDER_TYPE)
        self.assertEqual(by_guid["1002"]["state"], "out_of_pilot_scope")
        self.assertEqual(by_guid["1003"]["state"], "rejected")
        self.assertEqual(by_guid["1003"]["reason"], "host_outside_approved_source")

    def test_canonicalises_leaked_port_and_scheme(self):
        parsed = parser.parse_disclosure_rss(RSS, feed_url=FEED_URL, source_id="hnx", registry=REG)
        row = next(r for r in parsed["items"] if r["guid"] == "1001")
        self.assertEqual(row["canonical_url"], "https://www.hnx.vn/tin-cung-cap-rss-vi_vn-1001-0.html")

    def test_unknown_source_id_raises(self):
        with self.assertRaises(ValueError):
            parser.parse_disclosure_rss(RSS, feed_url=FEED_URL, source_id="nope", registry=REG)


class ParseDisclosureDetail(unittest.TestCase):
    def test_individual_registration_complete(self):
        detail = parser.parse_disclosure_detail(REGISTRATION_INDIVIDUAL, url="https://www.hnx.vn/x.html")
        self.assertTrue(detail["extraction_complete"])
        self.assertTrue(detail["content_block_found"])
        self.assertEqual(detail["ticker"], "AIG")
        self.assertEqual(detail["fields"]["actor_individual_name"], "Nguyễn Văn A")
        self.assertEqual(detail["fields"]["registered_sell_volume"]["shares"], 200000.0)
        self.assertIsNone(detail["fields"].get("registered_buy_volume"))
        self.assertEqual(detail["fields"]["shares_held_before"]["ownership_pct"], 8.48)
        self.assertEqual([], detail["unparsed_fields"])

    def test_execution_result_explicit_zero_and_related_persons(self):
        detail = parser.parse_disclosure_detail(EXECUTION_RESULT_ZERO, url="https://www.hnx.vn/x.html")
        self.assertTrue(detail["extraction_complete"])
        self.assertEqual(detail["ticker"], "VNF")
        self.assertEqual(detail["fields"]["executed_buy_volume"]["shares"], 0.0)
        self.assertEqual(detail["fields"]["registered_buy_volume"]["shares"], 1000000.0)
        self.assertEqual(detail["fields"]["non_execution_reason"],
                         "Giá thị trường biến động chưa phù hợp")
        self.assertEqual(len(detail["related_persons"]), 1)
        self.assertEqual(detail["related_persons"][0]["name"], "Người A")
        self.assertEqual(detail["related_persons"][0]["shares_held"]["shares"], 30160.0)

    def test_missing_br_between_bullets_still_separates_fields(self):
        """The real 2026-08-24 VNH page glues two bullets with no <br/> between them."""
        detail = parser.parse_disclosure_detail(MAJOR_HOLDER_GLUED, url="https://www.hnx.vn/x.html")
        self.assertEqual(detail["fields"]["actor_individual_name"], "Đỗ Đức Cường")
        self.assertEqual(detail["ticker"], "VNH")
        self.assertEqual([], detail["unparsed_fields"])

    def test_entity_registration_typo_label_recognised(self):
        """HNX's registration template spells this label without the final diacritic."""
        detail = parser.parse_disclosure_detail(ENTITY_REGISTRATION_TYPO_LABEL, url="https://www.hnx.vn/x.html")
        self.assertEqual(detail["fields"]["actor_entity_name"], "Công ty cổ phần Y")
        self.assertEqual(detail["ticker"], "IDV")

    def test_unmatched_structure_is_incomplete_not_falsely_complete(self):
        detail = parser.parse_disclosure_detail(FUND_CERT_UNMATCHED, url="https://www.hnx.vn/x.html")
        self.assertFalse(detail["content_block_found"])
        self.assertFalse(detail["extraction_complete"])
        self.assertEqual(detail["fields"], {})
        self.assertIsNone(detail["ticker"])


if __name__ == "__main__":
    unittest.main()
