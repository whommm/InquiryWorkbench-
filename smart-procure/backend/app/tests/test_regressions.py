import sys
import unittest

sys.path.append("smart-procure/backend")

from app.services.sheet_schema import locate_rows_by_criteria
from app.services.sheet_schema import build_sheet_schema
from app.services.excel_core import process_update
from app.models.types import UpdateAction


def _build_headers():
    base = ["序号", "物品名称", "品牌", "产品型号"]
    fields = ["品牌", "备注", "单价", "含税", "含运", "货期", "供应商"]
    headers = list(base)
    for s in (1, 2, 3):
        headers += [f"{f}{s}" for f in fields]
    return headers


class TestRegressions(unittest.TestCase):
    def test_schema_does_not_map_unit_as_supplier(self):
        headers = ["序号", "物品名称", "规格", "数量", "单位", "品牌", "供应商1", "单价1"]
        row = ["1", "西门子电机", "1KW", "10", "台", "西门子", None, None]
        sheet = [headers, row]
        schema = build_sheet_schema(sheet)
        slots = schema.get("slots") or {}
        supplier_idx = (slots.get(1) or {}).get("供应商")
        self.assertEqual(supplier_idx, headers.index("供应商1"))

    def test_locate_rows_brand_only_is_ambiguous(self):
        headers = _build_headers()
        row2 = ["1", "西门子电机", "西门子", "M1"] + [None] * (len(headers) - 4)
        row3 = ["2", "西门子风机", "西门子", "F1"] + [None] * (len(headers) - 4)
        sheet = [headers, row2, row3]

        out = locate_rows_by_criteria(sheet, brand="西门子", max_candidates=5)
        self.assertTrue(out.get("ambiguous"))
        self.assertGreaterEqual(len(out.get("candidates") or []), 2)

    def test_process_update_slot_shift_and_model_mismatch_remark(self):
        headers = _build_headers()
        row = ["1", "西门子电机", "西门子", "M1"] + [None] * (len(headers) - 4)

        def set_cell(col, val):
            row[headers.index(col)] = val

        set_cell("品牌1", "西门子")
        set_cell("单价1", 5200)
        set_cell("含税1", "是")
        set_cell("含运1", "是")
        set_cell("货期1", "5天")
        set_cell("供应商1", "旧供应商 旧人 111")

        sheet = [headers, row]
        action = UpdateAction(
            target_row=2,
            price=5000,
            tax=True,
            shipping=True,
            delivery_time="3天",
            supplier="新供应商 张三 17398716954",
            remarks=None,
            quoted_model="M2",
        )
        updated = process_update(sheet, action)
        urow = updated[1]

        self.assertEqual(urow[headers.index("单价1")], 5000.0)
        self.assertEqual(urow[headers.index("品牌1")], "西门子")
        self.assertEqual(urow[headers.index("供应商1")], "新供应商 张三 17398716954")
        self.assertEqual(urow[headers.index("单价2")], 5200)
        self.assertEqual(urow[headers.index("品牌2")], "西门子")
        self.assertEqual(urow[headers.index("供应商2")], "旧供应商 旧人 111")
        self.assertIn("型号不一致", str(urow[headers.index("备注1")]))

    def test_update_action_bool_parsing_zh(self):
        action = UpdateAction(
            target_row=2,
            price=5100,
            tax="含税",
            shipping="含运",
            delivery_time="3天",
        )
        self.assertTrue(action.tax)
        self.assertTrue(action.shipping)

    def test_process_update_spec_mismatch_goes_to_remark(self):
        base = ["序号", "物品名称", "规格", "数量", "单位", "品牌"]
        fields = ["品牌", "备注", "单价", "含税", "含运", "货期", "供应商"]
        headers = list(base)
        for s in (1, 2, 3):
            headers += [f"{f}{s}" for f in fields]

        row = ["1", "西门子电机", "1KW", "10", "台", "西门子"] + [None] * (len(headers) - len(base))
        sheet = [headers, row]
        action = UpdateAction(
            target_row=2,
            price=5100,
            tax=True,
            shipping=True,
            delivery_time="3天",
            supplier="电机贸易有限公司 张先生 18721309875",
            quoted_spec="2KW",
        )
        updated = process_update(sheet, action)
        urow = updated[1]
        self.assertIn("规格不一致", str(urow[headers.index("备注1")]))

    def test_process_update_spec_case_only_no_mismatch_remark(self):
        base = ["序号", "物品名称", "规格", "数量", "单位", "品牌"]
        fields = ["品牌", "备注", "单价", "含税", "含运", "货期", "供应商"]
        headers = list(base)
        for s in (1, 2, 3):
            headers += [f"{f}{s}" for f in fields]

        row = ["1", "西门子电机", "1KW", "10", "台", "西门子"] + [None] * (len(headers) - len(base))
        sheet = [headers, row]
        action = UpdateAction(
            target_row=2,
            price=5100,
            tax=True,
            shipping=True,
            delivery_time="3天",
            supplier="电机贸易有限公司 张先生 18721309875",
            quoted_spec="1kw",
        )
        updated = process_update(sheet, action)
        urow = updated[1]
        remark = str(urow[headers.index("备注1")] or "")
        self.assertNotIn("规格不一致", remark)

    def test_process_update_keeps_existing_slot3_when_slot2_empty(self):
        headers = _build_headers()
        row = ["1", "照明灯", "申创贝特", "GKL5109"] + [None] * (len(headers) - 4)

        def set_cell(col, val):
            row[headers.index(col)] = val

        set_cell("品牌1", "申创贝特")
        set_cell("单价1", 135)
        set_cell("含税1", "是")
        set_cell("含运1", "是")
        set_cell("货期1", "现货")
        set_cell("供应商1", "A")

        set_cell("品牌3", "申创贝特")
        set_cell("单价3", 140)
        set_cell("含税3", "是")
        set_cell("含运3", "是")
        set_cell("货期3", "2-3周")
        set_cell("供应商3", "C")

        sheet = [headers, row]
        action = UpdateAction(
            target_row=2,
            price=130,
            tax=True,
            shipping=True,
            delivery_time="现货",
            supplier="NEW",
        )
        updated = process_update(sheet, action)
        urow = updated[1]

        self.assertEqual(urow[headers.index("单价1")], 130.0)
        self.assertEqual(urow[headers.index("供应商1")], "NEW")
        self.assertEqual(urow[headers.index("单价2")], 135)
        self.assertEqual(urow[headers.index("供应商2")], "A")
        self.assertEqual(urow[headers.index("单价3")], 140)
        self.assertEqual(urow[headers.index("供应商3")], "C")

    def test_header_variants_and_shipping_text(self):
        base = ["序号", "物料名称", "品牌", "规格型号"]
        slot_fields = ["品牌", "单价", "是否含税", "是否含运", "货期", "备注", "供应商"]
        headers = list(base)
        for s in (1, 2, 3):
            headers += [f"{f}{s}" for f in slot_fields]

        row = ["1", "联轴器弹性体", "无品牌要求", "GR28"] + [None] * (len(headers) - len(base))

        def set_cell(col, val):
            row[headers.index(col)] = val

        set_cell("品牌1", "KTR-ROTEX")
        set_cell("单价1", 50)
        set_cell("是否含税1", "是")
        set_cell("是否含运1", "满1000包邮")
        set_cell("货期1", "现货")
        set_cell("供应商1", "供应商A")

        set_cell("品牌2", "KTR-ROTEX")
        set_cell("单价2", 60)
        set_cell("是否含税2", "是")
        set_cell("是否含运2", "是")
        set_cell("货期2", "现货")
        set_cell("供应商2", "供应商B")

        set_cell("品牌3", "KTR-ROTEX")
        set_cell("单价3", 70)
        set_cell("是否含税3", "是")
        set_cell("是否含运3", "是")
        set_cell("货期3", "现货")
        set_cell("供应商3", "供应商C")

        sheet = [headers, row]
        action = UpdateAction(
            target_row=2,
            price=40,
            tax=True,
            shipping="满1000包邮",
            delivery_time="现货",
            supplier="新供应商",
        )
        updated = process_update(sheet, action)
        urow = updated[1]
        self.assertEqual(urow[headers.index("单价1")], 40.0)
        self.assertEqual(urow[headers.index("是否含运1")], "满1000包邮")
        self.assertEqual(urow[headers.index("单价2")], 50)
        self.assertEqual(urow[headers.index("是否含运2")], "满1000包邮")
        self.assertEqual(urow[headers.index("单价3")], 60)


if __name__ == "__main__":
    unittest.main()

