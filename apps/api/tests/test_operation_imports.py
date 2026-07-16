import csv
import json
from decimal import Decimal
from io import BytesIO, StringIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.operation_imports import (
    InvalidFieldMappingError,
    InvalidOperationImportError,
    UnsafeOperationArchiveError,
    UnsupportedOperationImportTypeError,
    find_duplicate_fingerprints,
    is_csv_formula,
    normalize_external_url,
    parse_operation_import,
    protect_csv_cell,
    publication_match_key,
    resolve_field_mapping,
    source_fingerprint,
)


def _csv_bytes(rows: list[list[str]]) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def _xlsx_bytes(
    rows: list[list[str]],
    *,
    formulas: set[tuple[int, int]] | None = None,
    second_sheet: bool = False,
) -> bytes:
    formulas = formulas or set()
    sheet_rows: list[str] = []
    for row_number, row in enumerate(rows, start=1):
        cells: list[str] = []
        for column_index, value in enumerate(row):
            reference = f"{_column_letters(column_index)}{row_number}"
            escaped = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if (row_number, column_index) in formulas:
                cells.append(f'<c r="{reference}"><f>{escaped}</f><v>999</v></c>')
            else:
                cells.append(f'<c r="{reference}" t="inlineStr"><is><t>{escaped}</t></is></c>')
        sheet_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')

    sheets = [
        '<sheet name="数据" sheetId="1" r:id="rId1"/>',
    ]
    relationships = [
        (
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/>'
        )
    ]
    if second_sheet:
        sheets.append('<sheet name="忽略" sheetId="2" r:id="rId2"/>')
        relationships.append(
            '<Relationship Id="rId2" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/worksheet" Target="worksheets/sheet2.xml"/>'
        )

    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{''.join(sheets)}</sheets></workbook>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{''.join(relationships)}</Relationships>"
    )
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(sheet_rows)}</sheetData></worksheet>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        "</Types>"
    )

    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
        if second_sheet:
            archive.writestr(
                "xl/worksheets/sheet2.xml",
                (
                    '<worksheet xmlns="http://schemas.openxmlformats.org/'
                    'spreadsheetml/2006/main"><sheetData/></worksheet>'
                ),
            )
    return output.getvalue()


def _column_letters(index: int) -> str:
    value = index + 1
    letters = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def test_csv_import_maps_chinese_headers_and_normalizes_a_valid_row() -> None:
    data = _csv_bytes(
        [
            ["平台", "作品ID", "播放量", "点赞数", "销售额", "币种", "其他指标"],
            ["抖音", "douyin-123", "12,345", "88", "199.50", "人民币", '{"完播率": 0.42}'],
        ]
    )

    result = parse_operation_import(data, filename="运营数据.csv")

    assert result.import_kind == "csv"
    assert result.sheet_name is None
    assert len(result.valid_rows) == 1
    row = result.rows[0]
    assert row.row_number == 2
    assert row.normalized == {
        "platform": "douyin",
        "external_content_id": "douyin-123",
        "views": Decimal("12345"),
        "likes": Decimal("88"),
        "revenue_amount": Decimal("199.5"),
        "currency": "CNY",
        "extra_metrics": {"完播率": Decimal("0.42")},
    }
    assert row.publication_match_key == publication_match_key(
        platform="douyin",
        external_content_id="douyin-123",
    )
    assert len(row.source_fingerprint) == 64


def test_explicit_mapping_accepts_both_source_to_target_and_target_to_source() -> None:
    headers = ("渠道", "帖子编号", "曝光", "客单价")

    source_first = resolve_field_mapping(
        headers,
        {
            "渠道": "platform",
            "帖子编号": "external_content_id",
            "曝光": "views",
            "客单价": "extra_metrics.average_order_value",
        },
    )
    target_first = resolve_field_mapping(
        headers,
        {
            "platform": "渠道",
            "external_content_id": "帖子编号",
            "views": "曝光",
            "extra_metrics.average_order_value": "客单价",
        },
    )

    assert source_first == target_first
    assert source_first["客单价"] == "extra_metrics.average_order_value"


def test_mapping_rejects_unknown_headers_and_duplicate_targets() -> None:
    with pytest.raises(InvalidFieldMappingError):
        resolve_field_mapping(("平台",), {"不存在": "platform"})

    with pytest.raises(InvalidFieldMappingError, match="mapped more than once"):
        resolve_field_mapping(
            ("平台", "渠道"),
            {"平台": "platform", "渠道": "platform"},
        )


def test_exact_publication_matching_uses_id_then_url_and_never_title() -> None:
    by_id = publication_match_key(
        platform="小红书",
        external_content_id="note-1",
        external_url="HTTPS://Example.COM/post/1#fragment",
    )
    by_url = publication_match_key(
        platform="视频号",
        external_url="HTTPS://Example.COM:443/post/1#fragment",
    )

    assert (by_id.key_type, by_id.key_value) == ("external_content_id", "note-1")
    assert by_url.platform == "wechat_channels"
    assert (by_url.key_type, by_url.key_value) == (
        "external_url",
        "https://example.com/post/1",
    )
    with pytest.raises(ValueError, match="title matching is not supported"):
        publication_match_key(platform="douyin")


def test_title_alone_does_not_match_a_publication() -> None:
    result = parse_operation_import(
        _csv_bytes([["platform", "title", "views"], ["douyin", "当季番茄", "100"]]),
        filename="data.csv",
    )

    assert not result.rows[0].is_valid
    assert result.rows[0].publication_match_key is None
    assert "missing_publication_key" in {error.code for error in result.rows[0].errors}


def test_non_negative_metrics_currency_and_extra_metrics_are_validated_per_row() -> None:
    result = parse_operation_import(
        _csv_bytes(
            [
                ["platform", "content_id", "views", "revenue", "currency", "extra_metrics"],
                ["douyin", "one", "-1", "20", "", '{"watch_seconds": -3}'],
                ["douyin", "two", "NaN", "abc", "yuan", "[]"],
                ["douyin", "three", "10", "20", "HKD", '{"watch_seconds": 12.5}'],
            ]
        ),
        filename="data.csv",
    )

    first_codes = {error.code for error in result.rows[0].errors}
    second_codes = {error.code for error in result.rows[1].errors}
    assert {"negative_metric", "missing_currency"} <= first_codes
    assert {"invalid_number", "invalid_currency", "invalid_extra_metrics"} <= second_codes
    assert result.rows[2].is_valid
    assert result.rows[2].normalized["extra_metrics"] == {"watch_seconds": Decimal("12.5")}


def test_source_fingerprint_is_stable_and_detects_file_and_database_duplicates() -> None:
    first = source_fingerprint(
        {
            "platform": "douyin",
            "views": Decimal("10.0"),
            "extra_metrics": {"b": Decimal("2"), "a": Decimal("1")},
        }
    )
    second = source_fingerprint(
        {
            "extra_metrics": {"a": Decimal("1.0"), "b": Decimal("2.0")},
            "views": Decimal("10"),
            "platform": "douyin",
        }
    )
    assert first == second
    assert find_duplicate_fingerprints([first, second]) == {first}
    assert find_duplicate_fingerprints([first], existing_fingerprints=[first]) == {first}

    data = _csv_bytes(
        [
            ["platform", "content_id", "views"],
            ["douyin", "same", "10"],
            ["douyin", "same", "10.0"],
        ]
    )
    result = parse_operation_import(data, filename="data.csv")
    assert result.rows[0].is_valid
    assert result.rows[1].duplicate is True
    assert "duplicate_source_fingerprint" in {error.code for error in result.rows[1].errors}


def test_formula_like_csv_text_is_rejected_and_export_helper_neutralizes_it() -> None:
    result = parse_operation_import(
        _csv_bytes(
            [
                ["platform", "content_id", "title", "views"],
                ["douyin", "one", '=HYPERLINK("https://evil.invalid")', "10"],
                ["douyin", "two", "-1", "-1"],
            ]
        ),
        filename="data.csv",
    )

    assert "unsafe_csv_formula" in {error.code for error in result.rows[0].errors}
    assert "negative_metric" in {error.code for error in result.rows[1].errors}
    assert is_csv_formula("=2+2")
    assert is_csv_formula("@SUM(A1:A2)")
    assert not is_csv_formula("-12.5")
    assert protect_csv_cell("=2+2") == "'=2+2"
    assert protect_csv_cell("番茄") == "番茄"


def test_xlsx_import_uses_first_sheet_and_reports_formula_cells() -> None:
    data = _xlsx_bytes(
        [
            ["平台", "作品链接", "播放量", "标题"],
            ["视频号", "https://example.com/video/1", "120", "正常标题"],
            ["视频号", "https://example.com/video/2", "10", "=2+2"],
        ],
        formulas={(3, 3)},
        second_sheet=True,
    )

    result = parse_operation_import(data, filename="运营.xlsx")

    assert result.import_kind == "xlsx"
    assert result.sheet_name == "数据"
    assert "additional worksheet" in result.warnings[0]
    assert result.rows[0].is_valid
    assert result.rows[0].publication_match_key is not None
    assert "spreadsheet_formula_not_allowed" in {error.code for error in result.rows[1].errors}


def test_xlsx_shared_strings_are_supported() -> None:
    workbook = (
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    shared = (
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<si><t>platform</t></si><si><t>content_id</t></si>"
        "<si><t>douyin</t></si><si><t>shared-1</t></si></sst>"
    )
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1"><c r="A1" t="s"><v>0</v></c>'
        '<c r="B1" t="s"><v>1</v></c></row>'
        '<row r="2"><c r="A2" t="s"><v>2</v></c>'
        '<c r="B2" t="s"><v>3</v></c></row></sheetData></worksheet>'
    )
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/sharedStrings.xml", shared)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)

    result = parse_operation_import(output.getvalue(), filename="data.xlsx")

    assert result.rows[0].is_valid
    assert result.rows[0].normalized["external_content_id"] == "shared-1"


def test_xlsx_rejects_path_traversal_and_unsafe_compression() -> None:
    traversal = BytesIO()
    with ZipFile(traversal, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/_rels/workbook.xml.rels", "<Relationships/>")
        archive.writestr("../escape.xml", "<bad/>")
    with pytest.raises(UnsafeOperationArchiveError, match="Unsafe XLSX archive path"):
        parse_operation_import(traversal.getvalue(), filename="bad.xlsx")

    bomb = BytesIO()
    with ZipFile(bomb, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/_rels/workbook.xml.rels", "<Relationships/>")
        archive.writestr("xl/media/bomb.bin", b"A" * 1_100_000)
    with pytest.raises(UnsafeOperationArchiveError, match="compression ratio"):
        parse_operation_import(bomb.getvalue(), filename="bomb.xlsx")


def test_rejects_legacy_xls_non_utf8_csv_and_invalid_urls() -> None:
    with pytest.raises(UnsupportedOperationImportTypeError, match=r"\.xls"):
        parse_operation_import(b"legacy", filename="old.xls")
    with pytest.raises(InvalidOperationImportError, match="UTF-8"):
        parse_operation_import(b"\xff\xfe\x00", filename="bad.csv")
    with pytest.raises(ValueError, match="absolute HTTP"):
        normalize_external_url("javascript:alert(1)")
    with pytest.raises(ValueError, match="credentials"):
        normalize_external_url("https://user:pass@example.com/video")


def test_csv_limits_duplicate_headers_and_extra_values_are_rejected() -> None:
    with pytest.raises(InvalidFieldMappingError, match="unique"):
        parse_operation_import(
            _csv_bytes([["Platform", " platform "], ["douyin", "douyin"]]),
            filename="duplicate.csv",
        )
    with pytest.raises(InvalidOperationImportError, match="more values"):
        parse_operation_import(
            _csv_bytes([["platform"], ["douyin", "extra"]]),
            filename="wide.csv",
        )
    with pytest.raises(InvalidOperationImportError, match="row limit"):
        parse_operation_import(
            _csv_bytes(
                [
                    ["platform", "content_id"],
                    ["douyin", "one"],
                    ["douyin", "two"],
                ]
            ),
            filename="rows.csv",
            max_rows=1,
        )


def test_result_can_be_serialized_after_decimal_conversion_for_a_service_layer() -> None:
    result = parse_operation_import(
        _csv_bytes([["platform", "content_id", "views"], ["douyin", "one", "10.5"]]),
        filename="data.csv",
    )

    payload = {
        "fingerprint": result.rows[0].source_fingerprint,
        "normalized": {
            key: format(value, "f") if isinstance(value, Decimal) else value
            for key, value in result.rows[0].normalized.items()
        },
    }
    assert json.loads(json.dumps(payload))["normalized"]["views"] == "10.5"
