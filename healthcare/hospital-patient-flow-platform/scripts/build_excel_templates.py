#!/usr/bin/env python3
"""Build the Excel import templates handed to hospital data teams.

One workbook per dataset, each containing:

  Instructions   what the file is for, how to fill it, who to ask
  Data           the header row, formatted and frozen, with dropdowns
  Data dictionary every field, its type, whether it is required, and the
                 accepted values
  Example        two filled rows showing the expected formats

The dropdowns and the dictionary sheet are generated from the same
``DatasetSpec`` the loader validates against, so a template can never
drift from the rules that will be applied to it.

Usage:
    python scripts/build_excel_templates.py --out data/templates
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.ingest.datasets import DATASETS, LOAD_ORDER, DatasetSpec   # noqa: E402

HEADER_FILL = PatternFill("solid", fgColor="0F3B5C")
REQUIRED_FILL = PatternFill("solid", fgColor="C00000")
TITLE_FONT = Font(size=15, bold=True, color="0F3B5C")
HEADER_FONT = Font(bold=True, color="FFFFFF")
NOTE_FONT = Font(italic=True, color="595959")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

TYPE_HINTS = {
    "string": "Text",
    "integer": "Whole number",
    "number": "Decimal number",
    "boolean": "Y or N",
    "datetime": "Date and time (YYYY-MM-DD HH:MM)",
    "date": "Date (YYYY-MM-DD)",
}


def _autosize(sheet, widths: dict[int, int]) -> None:
    for column, width in widths.items():
        sheet.column_dimensions[get_column_letter(column)].width = width


def _instructions_sheet(workbook: Workbook, spec: DatasetSpec) -> None:
    sheet = workbook.create_sheet("Instructions", 0)
    sheet["A1"] = spec.title_en
    sheet["A1"].font = TITLE_FONT
    sheet["A2"] = spec.title_ar
    sheet["A2"].font = Font(size=12, color="0F3B5C")
    sheet["A2"].alignment = Alignment(horizontal="right")

    lines = [
        "",
        "How to use this template",
        "1. Export the data from your HIS into the 'Data' sheet, one row per record.",
        "2. Do not rename, reorder or delete the header row -- the loader reads it.",
        "3. Extra columns are allowed. They are reported as unmapped and ignored.",
        "4. Leave a cell blank when the value is genuinely unknown. Do not type 'N/A',",
        "   'unknown' or a placeholder date such as 01/01/1900.",
        "5. Save as .xlsx or .csv and upload it in the platform's Import screen.",
        "",
        "Before you upload",
        f"* Required fields: {', '.join(spec.required_fields) or 'none'}.",
        f"* Each record is identified by: {' + '.join(spec.natural_key)}.",
        "  Repeating that key means the later row is quarantined as a duplicate.",
    ]
    if spec.references_encounter:
        lines.append("* Load the 'encounters' file for this period FIRST. Rows referring to")
        lines.append("  an unknown encounter number cannot be loaded.")
    if spec.notes:
        lines += ["", f"Note: {spec.notes}"]

    lines += [
        "",
        "Dates and times",
        "* Any consistent format works -- the loader detects it from the column.",
        "* Keep one format per column. Mixing 01/02/2026 and 2026-02-01 in the same",
        "  column is the most common cause of a rejected batch.",
        "* Arabic-Indic digits are accepted and converted automatically.",
        "",
        "What happens after upload",
        "* Every file is profiled, validated and scored before any row is stored.",
        "* You receive a data quality report listing each issue, the rows affected",
        "  and what the platform did about it.",
        "* Rows with unusable values are quarantined; the rest still load.",
        "* Any load can be reversed in full by its batch number.",
        "",
        "Patient identifiers",
        "* Medical record numbers are hashed on arrival and never stored in readable",
        "  form. Do not include patient names, national IDs, addresses or phone",
        "  numbers in any column -- they are not needed and must not be sent.",
    ]

    for offset, text in enumerate(lines, start=4):
        cell = sheet.cell(row=offset, column=1, value=text)
        if text and not text.startswith((" ", "*", "1", "2", "3", "4", "5")):
            cell.font = Font(bold=True, color="0F3B5C")
    _autosize(sheet, {1: 95})


def _data_sheet(workbook: Workbook, spec: DatasetSpec) -> None:
    sheet = workbook.create_sheet("Data", 1)

    for column, field in enumerate(spec.fields, start=1):
        cell = sheet.cell(row=1, column=column, value=field.name)
        cell.font = HEADER_FONT
        cell.fill = REQUIRED_FILL if field.required else HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
        sheet.column_dimensions[get_column_letter(column)].width = max(len(field.name) + 4, 16)

        # Dropdowns for closed code sets. Excel caps an inline list at 255
        # characters, so longer sets fall back to the dictionary sheet.
        if field.domain:
            joined = ",".join(field.domain)
            if len(joined) <= 250:
                validation = DataValidation(
                    type="list", formula1=f'"{joined}"', allow_blank=True,
                    showErrorMessage=not field.required,
                )
                validation.error = f"Value must be one of: {joined}"
                validation.errorTitle = f"Invalid {field.name}"
                sheet.add_data_validation(validation)
                letter = get_column_letter(column)
                validation.add(f"{letter}2:{letter}5000")

    sheet.freeze_panes = "A2"
    sheet.row_dimensions[1].height = 32


def _dictionary_sheet(workbook: Workbook, spec: DatasetSpec) -> None:
    sheet = workbook.create_sheet("Data dictionary", 2)
    headers = ["Field", "Type", "Required", "Accepted values", "Range",
               "Also recognised as", "Description"]
    for column, header in enumerate(headers, start=1):
        cell = sheet.cell(row=1, column=column, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.border = BORDER

    for row, field in enumerate(spec.fields, start=2):
        bounds = ""
        if field.minimum is not None or field.maximum is not None:
            bounds = f"{field.minimum if field.minimum is not None else '-'} to " \
                     f"{field.maximum if field.maximum is not None else '-'}"
        values = [
            field.name,
            TYPE_HINTS.get(field.dtype, field.dtype),
            "Yes" if field.required else "No",
            ", ".join(field.domain) if field.domain else "",
            bounds,
            ", ".join(field.aliases[:6]),
            field.description,
        ]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=row, column=column, value=value)
            cell.alignment = Alignment(vertical="top", wrap_text=column in (4, 6, 7))
            cell.border = BORDER
            if column == 3 and field.required:
                cell.font = Font(bold=True, color="C00000")

    sheet.freeze_panes = "A2"
    _autosize(sheet, {1: 26, 2: 28, 3: 10, 4: 38, 5: 14, 6: 40, 7: 55})


def _example_sheet(workbook: Workbook, spec: DatasetSpec) -> None:
    sheet = workbook.create_sheet("Example", 3)
    sheet["A1"] = "Two filled rows showing the expected formats. Delete this sheet before upload."
    sheet["A1"].font = NOTE_FONT

    for column, field in enumerate(spec.fields, start=1):
        cell = sheet.cell(row=3, column=column, value=field.name)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.border = BORDER
        sheet.column_dimensions[get_column_letter(column)].width = max(len(field.name) + 4, 18)

    base = datetime(2026, 3, 1, 8, 0)
    for offset in range(2):
        for column, field in enumerate(spec.fields, start=1):
            sheet.cell(row=4 + offset, column=column,
                       value=_example_value(field, offset, base))
    sheet.freeze_panes = "A4"


def _example_value(field, offset: int, base: datetime):
    if field.dtype in ("datetime", "date"):
        stamp = base + timedelta(days=offset, minutes=17 * offset)
        return stamp.strftime("%Y-%m-%d %H:%M" if field.dtype == "datetime" else "%Y-%m-%d")
    if field.domain:
        return field.domain[offset % len(field.domain)]
    if field.dtype == "integer":
        low = int(field.minimum) if field.minimum is not None else 1
        return low + offset
    if field.dtype == "number":
        return round(12.5 + offset * 3.25, 2)
    if field.dtype == "boolean":
        return "N" if offset else "Y"
    if field.name.endswith(("_no", "_ref")):
        return f"{field.name.split('_')[0].upper()[:3]}{1001 + offset}"
    if field.name == "mrn":
        return f"MRN{100045 + offset}"
    if field.name.endswith("_code"):
        return "W1" if offset == 0 else "ICU1"
    return f"Example {offset + 1}"


def build(spec: DatasetSpec, out_dir: Path) -> Path:
    workbook = Workbook()
    workbook.remove(workbook.active)          # drop the default empty sheet

    _instructions_sheet(workbook, spec)
    _data_sheet(workbook, spec)
    _dictionary_sheet(workbook, spec)
    _example_sheet(workbook, spec)

    path = out_dir / f"template_{spec.key}.xlsx"
    workbook.save(path)
    return path


def build_combined(out_dir: Path) -> Path:
    """One workbook with every dataset as a sheet, for smaller hospitals."""
    workbook = Workbook()
    workbook.remove(workbook.active)

    overview = workbook.create_sheet("Read me first", 0)
    overview["A1"] = "Hospital Patient Flow Platform -- combined import workbook"
    overview["A1"].font = TITLE_FONT
    rows = [
        "",
        "Each sheet below is one dataset. Fill only the sheets you have data for.",
        "",
        "Load them in this order -- later datasets reference earlier ones:",
    ]
    for position, key in enumerate(LOAD_ORDER, start=1):
        spec = DATASETS[key]
        rows.append(f"   {position}. {key}  --  {spec.title_en}")
    rows += [
        "",
        "Required fields are shown with a red header. Every other column may be",
        "left blank; the affected indicators are simply reported as unavailable",
        "rather than silently computed on partial data.",
        "",
        "Per-dataset workbooks with dropdowns, a data dictionary and worked",
        "examples are in the same folder as this file.",
    ]
    for offset, text in enumerate(rows, start=3):
        overview.cell(row=offset, column=1, value=text)
    _autosize(overview, {1: 90})

    for key in LOAD_ORDER:
        spec = DATASETS[key]
        sheet = workbook.create_sheet(key[:31])
        for column, field in enumerate(spec.fields, start=1):
            cell = sheet.cell(row=1, column=column, value=field.name)
            cell.font = HEADER_FONT
            cell.fill = REQUIRED_FILL if field.required else HEADER_FILL
            cell.border = BORDER
            sheet.column_dimensions[get_column_letter(column)].width = max(len(field.name) + 4, 16)
        sheet.freeze_panes = "A2"

    path = out_dir / "hospital_import_templates.xlsx"
    workbook.save(path)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="data/templates", help="Output directory")
    parser.add_argument("--dataset", help="Build a single dataset instead of all")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    keys = [args.dataset] if args.dataset else list(LOAD_ORDER)
    unknown = [k for k in keys if k not in DATASETS]
    if unknown:
        print(f"Unknown dataset(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Available: {', '.join(sorted(DATASETS))}", file=sys.stderr)
        return 1

    for key in keys:
        path = build(DATASETS[key], out_dir)
        spec = DATASETS[key]
        print(f"  {path.name:42s} {len(spec.fields):>2} fields, "
              f"{len(spec.required_fields)} required")

    if not args.dataset:
        combined = build_combined(out_dir)
        print(f"  {combined.name:42s} all {len(LOAD_ORDER)} datasets")

    print(f"\nTemplates written to {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
