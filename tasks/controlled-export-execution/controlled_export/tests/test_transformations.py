import io

from django.test import SimpleTestCase, override_settings
from openpyxl import Workbook, load_workbook

from controlled_export.errors import ContractError, UnsupportedContent
from controlled_export.transformations import transform_csv, transform_xlsx

from .helpers import csv_bytes, csv_plan


@override_settings(CONTROLLED_EXPORT_MAX_INPUT_BYTES=1024 * 1024, CONTROLLED_EXPORT_MAX_ROWS=100)
class TransformationTests(SimpleTestCase):
    def test_csv_is_scoped_masked_and_formula_neutralized(self):
        result = transform_csv(csv_bytes(), csv_plan(), "mask")
        self.assertEqual(
            result.content.decode("utf-8").splitlines(),
            ["name,email,note", "Alice,***,'=1+1"],
        )
        self.assertEqual(result.output_records, 1)

    def test_csv_rejects_columns_outside_authorized_scope(self):
        plan = csv_plan()
        plan["operations"][0]["columns"] = ["secret"]
        with self.assertRaises(ContractError):
            transform_csv(csv_bytes(), plan, "mask")

    def _workbook_bytes(self, *, hidden=False, formula=False, hyperlink=False):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Export"
        sheet.append(["name", "email", "note"])
        sheet.append(["Synthetic User", "user@example.invalid", "=2+2" if formula else "safe"])
        if hidden:
            sheet.column_dimensions["B"].hidden = True
        if hyperlink:
            sheet["C2"].hyperlink = "https://example.invalid"
        output = io.BytesIO()
        workbook.save(output)
        return output.getvalue()

    def _xlsx_plan(self):
        return {
            "version": "1",
            "format": "xlsx",
            "scope": {"worksheets": ["Export"], "columns": ["name", "email", "note"]},
            "operations": [
                {"type": "mask_columns", "columns": ["email"], "strategy": "fixed", "value": "***"},
                {"type": "sanitize_formulas"},
            ],
        }

    def test_xlsx_is_rebuilt_with_only_selected_content(self):
        result = transform_xlsx(self._workbook_bytes(), self._xlsx_plan(), "mask")
        workbook = load_workbook(io.BytesIO(result.content), data_only=False)
        self.assertEqual(workbook.sheetnames, ["Export"])
        self.assertEqual(workbook["Export"]["B2"].value, "***")
        self.assertEqual(workbook["Export"]["C2"].value, "safe")
        workbook.close()

    def test_xlsx_rejects_hidden_formula_and_hyperlink_channels(self):
        for options in ({"hidden": True}, {"formula": True}, {"hyperlink": True}):
            with self.subTest(options=options), self.assertRaises(UnsupportedContent):
                transform_xlsx(self._workbook_bytes(**options), self._xlsx_plan(), "mask")
