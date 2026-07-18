"""Pure parsing and validation for offline operation-data imports.

The module intentionally does not query or mutate the database.  It turns CSV
or XLSX bytes into normalized rows that a later service layer can match to a
``Publication`` using only an exact platform plus external ID or URL key.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from pathlib import PurePosixPath
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

ImportKind = Literal["csv", "xlsx"]

CSV_MEDIA_TYPES = frozenset(
    {
        "text/csv",
        "application/csv",
        "application/vnd.ms-excel",
    }
)
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

DEFAULT_MAX_ROWS = 10_000
DEFAULT_MAX_COLUMNS = 200
DEFAULT_MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_XLSX_MEMBERS = 2_000
MAX_XLSX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_XLSX_COMPRESSION_RATIO = 200
MAX_CELL_CHARACTERS = 32_000

_XLSX_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_XML_NS = {"x": _XLSX_MAIN_NS, "r": _PACKAGE_REL_NS}

_METRIC_FIELDS = frozenset(
    {
        "views",
        "likes",
        "comments",
        "shares",
        "saves",
        "clicks",
        "orders",
        "followers_gained",
    }
)
_DECIMAL_FIELDS = _METRIC_FIELDS | {"revenue_amount"}
_TEXT_FIELDS = frozenset(
    {
        "platform",
        "external_content_id",
        "external_url",
        "published_at",
        "currency",
        "title",
        "extra_metrics",
    }
)
CANONICAL_FIELDS = _DECIMAL_FIELDS | _TEXT_FIELDS

_ALIASES: dict[str, tuple[str, ...]] = {
    "platform": ("platform", "平台", "發布平台", "发布平台"),
    "external_content_id": (
        "external_content_id",
        "content_id",
        "post_id",
        "video_id",
        "作品id",
        "内容id",
        "內容id",
        "视频id",
        "影片id",
    ),
    "external_url": (
        "external_url",
        "content_url",
        "post_url",
        "video_url",
        "url",
        "作品链接",
        "作品連結",
        "发布链接",
        "發布連結",
    ),
    "published_at": ("published_at", "publish_time", "发布时间", "發布時間"),
    "title": ("title", "标题", "標題"),
    "views": ("views", "view_count", "plays", "播放量", "观看量", "觀看量"),
    "likes": ("likes", "like_count", "点赞数", "點讚數", "赞", "讚"),
    "comments": ("comments", "comment_count", "评论数", "評論數"),
    "shares": ("shares", "share_count", "分享数", "分享數", "转发数", "轉發數"),
    "saves": ("saves", "save_count", "收藏数", "收藏數"),
    "clicks": ("clicks", "click_count", "点击数", "點擊數"),
    "orders": ("orders", "order_count", "订单数", "訂單數"),
    "followers_gained": (
        "followers_gained",
        "new_followers",
        "涨粉",
        "漲粉",
        "新增粉丝",
        "新增粉絲",
    ),
    "revenue_amount": (
        "revenue_amount",
        "amount",
        "revenue",
        "gmv",
        "销售额",
        "銷售額",
        "成交金额",
        "成交金額",
    ),
    "currency": ("currency", "币种", "幣種", "货币", "貨幣"),
    "extra_metrics": ("extra_metrics", "其他指标", "其他指標"),
}
_PLATFORM_ALIASES = {
    "douyin": "douyin",
    "抖音": "douyin",
    "xiaohongshu": "xiaohongshu",
    "小红书": "xiaohongshu",
    "小紅書": "xiaohongshu",
    "red": "xiaohongshu",
    "wechat_channels": "wechat_channels",
    "wechat-channels": "wechat_channels",
    "channels": "wechat_channels",
    "视频号": "wechat_channels",
    "視頻號": "wechat_channels",
}
_CURRENCY_ALIASES = {
    "人民币": "CNY",
    "人民幣": "CNY",
    "rmb": "CNY",
    "￥": "CNY",
    "¥": "CNY",
    "港币": "HKD",
    "港幣": "HKD",
    "美元": "USD",
}
# Keep the source file UTF-8 and explicitly add the production-facing Simplified
# Chinese and Hong Kong Traditional Chinese headers.  Some spreadsheet exporters
# use visually similar variants, so aliases are intentionally broader than the
# canonical UI labels.
_ALIASES.update(
    {
        "platform": ("platform", "平台", "发布平台", "發佈平台"),
        "external_content_id": (
            "external_content_id",
            "content_id",
            "post_id",
            "video_id",
            "作品id",
            "作品ID",
            "内容id",
            "內容id",
            "视频id",
            "影片id",
        ),
        "external_url": (
            "external_url",
            "content_url",
            "post_url",
            "video_url",
            "url",
            "作品链接",
            "作品連結",
            "发布链接",
            "發佈連結",
        ),
        "published_at": (
            "published_at",
            "publish_time",
            "发布时间",
            "發佈時間",
        ),
        "title": ("title", "标题", "標題"),
        "views": ("views", "view_count", "plays", "播放量", "观看量", "觀看量"),
        "likes": ("likes", "like_count", "点赞数", "點讚數", "赞", "讚"),
        "comments": ("comments", "comment_count", "评论数", "評論數"),
        "shares": ("shares", "share_count", "分享数", "分享數", "转发数", "轉發數"),
        "saves": ("saves", "save_count", "收藏数", "收藏數"),
        "clicks": ("clicks", "click_count", "点击数", "點擊數"),
        "orders": ("orders", "order_count", "订单数", "訂單數"),
        "followers_gained": (
            "followers_gained",
            "new_followers",
            "涨粉",
            "漲粉",
            "新增粉丝",
            "新增粉絲",
        ),
        "revenue_amount": (
            "revenue_amount",
            "amount",
            "revenue",
            "gmv",
            "销售额",
            "銷售額",
            "成交金额",
            "成交金額",
        ),
        "currency": ("currency", "币种", "幣種", "货币", "貨幣"),
        "extra_metrics": ("extra_metrics", "其他指标", "其他指標"),
    }
)
_PLATFORM_ALIASES.update(
    {
        "抖音": "douyin",
        "小红书": "xiaohongshu",
        "小紅書": "xiaohongshu",
        "视频号": "wechat_channels",
        "視頻號": "wechat_channels",
    }
)
_CURRENCY_ALIASES.update(
    {
        "人民币": "CNY",
        "人民幣": "CNY",
        "元": "CNY",
        "¥": "CNY",
        "港币": "HKD",
        "港幣": "HKD",
        "美元": "USD",
    }
)

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_CELL_REFERENCE_RE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")
_DANGEROUS_CSV_PREFIXES = ("=", "+", "@", "\t", "\r", "\n")


class OperationImportError(ValueError):
    """Base error for an invalid import file or parser request."""

    status_code = 422
    code = "operation_import_error"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class EmptyOperationImportError(OperationImportError):
    status_code = 400
    code = "empty_operation_import"


class UnsupportedOperationImportTypeError(OperationImportError):
    status_code = 415
    code = "unsupported_operation_import_type"


class InvalidOperationImportError(OperationImportError):
    code = "invalid_operation_import"


class UnsafeOperationArchiveError(OperationImportError):
    code = "unsafe_operation_archive"


class InvalidFieldMappingError(OperationImportError):
    status_code = 400
    code = "invalid_field_mapping"


@dataclass(frozen=True, slots=True)
class RowValidationError:
    code: str
    message: str
    field: str | None = None
    value: str | None = None


@dataclass(frozen=True, slots=True)
class PublicationMatchKey:
    platform: str
    key_type: Literal["external_content_id", "external_url"]
    key_value: str


@dataclass(frozen=True, slots=True)
class OperationImportRow:
    row_number: int
    source_values: Mapping[str, str]
    normalized: Mapping[str, Any]
    errors: tuple[RowValidationError, ...]
    source_fingerprint: str
    publication_match_key: PublicationMatchKey | None
    duplicate: bool = False

    @property
    def is_valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class OperationImportResult:
    import_kind: ImportKind
    sheet_name: str | None
    headers: tuple[str, ...]
    field_mapping: Mapping[str, str]
    rows: tuple[OperationImportRow, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def valid_rows(self) -> tuple[OperationImportRow, ...]:
        return tuple(row for row in self.rows if row.is_valid)

    @property
    def invalid_rows(self) -> tuple[OperationImportRow, ...]:
        return tuple(row for row in self.rows if not row.is_valid)


@dataclass(frozen=True, slots=True)
class _ParsedTable:
    import_kind: ImportKind
    sheet_name: str | None
    headers: tuple[str, ...]
    rows: tuple[tuple[int, tuple[str, ...], frozenset[int]], ...]
    warnings: tuple[str, ...]


def parse_operation_import(
    data: bytes,
    *,
    filename: str | None = None,
    media_type: str | None = None,
    field_mapping: Mapping[str, str] | None = None,
    existing_fingerprints: Iterable[str] = (),
    max_rows: int = DEFAULT_MAX_ROWS,
    max_columns: int = DEFAULT_MAX_COLUMNS,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> OperationImportResult:
    """Parse CSV/XLSX bytes and return normalized, independently validatable rows.

    ``field_mapping`` accepts either ``source header -> canonical field`` or
    ``canonical field -> source header``.  Extra metric targets use
    ``extra_metrics.<metric_name>``.
    """

    _validate_positive_limit("max_rows", max_rows)
    _validate_positive_limit("max_columns", max_columns)
    _validate_positive_limit("max_file_bytes", max_file_bytes)
    if not data:
        raise EmptyOperationImportError("The uploaded operation-data file is empty.")
    if len(data) > max_file_bytes:
        raise InvalidOperationImportError(
            f"The uploaded file exceeds the {max_file_bytes}-byte processing limit."
        )

    import_kind = _detect_import_kind(data, filename=filename, media_type=media_type)
    if import_kind == "csv":
        table = _parse_csv(data, max_rows=max_rows, max_columns=max_columns)
    else:
        table = _parse_xlsx(data, max_rows=max_rows, max_columns=max_columns)

    resolved_mapping = resolve_field_mapping(table.headers, field_mapping)
    known_fingerprints = {value.strip().lower() for value in existing_fingerprints if value.strip()}
    seen_fingerprints: set[str] = set()
    normalized_rows: list[OperationImportRow] = []
    for row_number, values, formula_columns in table.rows:
        source_values = {
            header: values[index] if index < len(values) else ""
            for index, header in enumerate(table.headers)
        }
        normalized, errors = _normalize_row(
            source_values,
            resolved_mapping,
            formula_headers={
                table.headers[index] for index in formula_columns if index < len(table.headers)
            },
        )
        match_key: PublicationMatchKey | None = None
        if not any(error.code in {"missing_platform", "invalid_platform"} for error in errors):
            try:
                match_key = publication_match_key(
                    platform=str(normalized.get("platform", "")),
                    external_content_id=_optional_text(normalized.get("external_content_id")),
                    external_url=_optional_text(normalized.get("external_url")),
                )
            except ValueError as exc:
                errors.append(
                    RowValidationError(
                        code="missing_publication_key",
                        field="external_content_id",
                        message=str(exc),
                    )
                )

        fingerprint = source_fingerprint(normalized)
        duplicate = fingerprint in known_fingerprints or fingerprint in seen_fingerprints
        if duplicate:
            errors.append(
                RowValidationError(
                    code="duplicate_source_fingerprint",
                    field="source_fingerprint",
                    message="This normalized source row has already been imported or repeated.",
                    value=fingerprint,
                )
            )
        seen_fingerprints.add(fingerprint)
        normalized_rows.append(
            OperationImportRow(
                row_number=row_number,
                source_values=source_values,
                normalized=normalized,
                errors=tuple(errors),
                source_fingerprint=fingerprint,
                publication_match_key=match_key,
                duplicate=duplicate,
            )
        )

    return OperationImportResult(
        import_kind=table.import_kind,
        sheet_name=table.sheet_name,
        headers=table.headers,
        field_mapping=resolved_mapping,
        rows=tuple(normalized_rows),
        warnings=table.warnings,
    )


def resolve_field_mapping(
    headers: Sequence[str],
    field_mapping: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return a ``source header -> canonical target`` mapping."""

    normalized_headers = tuple(header.strip() for header in headers)
    if not normalized_headers or any(not header for header in normalized_headers):
        raise InvalidFieldMappingError("Every imported column must have a non-empty header.")
    if len(set(normalized_headers)) != len(normalized_headers):
        raise InvalidFieldMappingError("Imported column headers must be unique.")

    header_lookup = {_header_key(header): header for header in normalized_headers}
    if len(header_lookup) != len(normalized_headers):
        raise InvalidFieldMappingError("Imported column headers must be unique ignoring case.")

    if field_mapping is None:
        resolved: dict[str, str] = {}
        for canonical, aliases in _ALIASES.items():
            for alias in aliases:
                source = header_lookup.get(_header_key(alias))
                if source is not None:
                    resolved[source] = canonical
                    break
        return resolved

    resolved = {}
    used_targets: set[str] = set()
    for raw_left, raw_right in field_mapping.items():
        left = str(raw_left).strip()
        right = str(raw_right).strip()
        left_is_target = _is_mapping_target(left)
        right_is_target = _is_mapping_target(right)
        left_header = header_lookup.get(_header_key(left))
        right_header = header_lookup.get(_header_key(right))

        if left_header is not None and right_is_target and not left_is_target:
            source, target = left_header, right
        elif right_header is not None and left_is_target and not right_is_target:
            source, target = right_header, left
        elif left_header is not None and right_is_target:
            source, target = left_header, right
        elif right_header is not None and left_is_target:
            source, target = right_header, left
        else:
            raise InvalidFieldMappingError(
                f"Field mapping entry {left!r}: {right!r} must pair an imported header "
                "with a canonical field."
            )

        target = _normalize_mapping_target(target)
        if source in resolved:
            raise InvalidFieldMappingError(f"Imported column {source!r} is mapped more than once.")
        if target in used_targets:
            raise InvalidFieldMappingError(f"Canonical field {target!r} is mapped more than once.")
        resolved[source] = target
        used_targets.add(target)
    return resolved


def publication_match_key(
    *,
    platform: str,
    external_content_id: str | None = None,
    external_url: str | None = None,
) -> PublicationMatchKey:
    """Build the only supported exact matching key for a ``Publication``."""

    normalized_platform = normalize_platform(platform)
    content_id = (external_content_id or "").strip()
    if content_id:
        return PublicationMatchKey(
            platform=normalized_platform,
            key_type="external_content_id",
            key_value=content_id,
        )
    url = (external_url or "").strip()
    if url:
        return PublicationMatchKey(
            platform=normalized_platform,
            key_type="external_url",
            key_value=normalize_external_url(url),
        )
    raise ValueError(
        "Exact Publication matching requires platform plus external_content_id or external_url; "
        "title matching is not supported."
    )


def source_fingerprint(normalized_row: Mapping[str, Any]) -> str:
    """Return a stable SHA-256 helper for duplicate detection."""

    canonical = _json_safe(normalized_row)
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def find_duplicate_fingerprints(
    fingerprints: Iterable[str],
    *,
    existing_fingerprints: Iterable[str] = (),
) -> frozenset[str]:
    """Return repeated or previously known fingerprints."""

    known = {item.strip().lower() for item in existing_fingerprints if item.strip()}
    seen: set[str] = set()
    duplicates: set[str] = set()
    for raw in fingerprints:
        value = raw.strip().lower()
        if not value:
            continue
        if value in known or value in seen:
            duplicates.add(value)
        seen.add(value)
    return frozenset(duplicates)


def is_csv_formula(value: str) -> bool:
    """Return whether a text cell could execute when exported to a spreadsheet."""

    if not value:
        return False
    stripped = value.lstrip(" ")
    if not stripped:
        return False
    if stripped[0] in _DANGEROUS_CSV_PREFIXES:
        return True
    return stripped.startswith("-") and not _is_plain_number(stripped)


def protect_csv_cell(value: Any) -> str:
    """Neutralize spreadsheet formula prefixes for any later CSV export."""

    text = "" if value is None else str(value)
    return f"'{text}" if is_csv_formula(text) else text


def normalize_platform(value: str) -> str:
    normalized = value.strip().casefold().replace(" ", "_")
    try:
        return _PLATFORM_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(f"Unsupported platform: {value!r}.") from exc


def normalize_external_url(value: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("external_url must be an absolute HTTP or HTTPS URL.")
    if parsed.username or parsed.password:
        raise ValueError("external_url must not contain embedded credentials.")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("external_url must contain a valid host.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("external_url contains an invalid port.") from exc
    default_port = (parsed.scheme.lower() == "http" and port == 80) or (
        parsed.scheme.lower() == "https" and port == 443
    )
    netloc = hostname.encode("idna").decode("ascii").lower()
    if port is not None and not default_port:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def _normalize_row(
    source_values: Mapping[str, str],
    field_mapping: Mapping[str, str],
    *,
    formula_headers: set[str],
) -> tuple[dict[str, Any], list[RowValidationError]]:
    normalized: dict[str, Any] = {}
    errors: list[RowValidationError] = []
    extra_metrics: dict[str, Decimal] = {}

    for source, target in field_mapping.items():
        raw = source_values.get(source, "").strip()
        if not raw:
            continue
        if source in formula_headers:
            errors.append(
                RowValidationError(
                    code="spreadsheet_formula_not_allowed",
                    field=target,
                    message="Spreadsheet formulas are not accepted as imported values.",
                    value=raw,
                )
            )
            continue
        if is_csv_formula(raw) and not (target in _DECIMAL_FIELDS and _is_plain_number(raw)):
            errors.append(
                RowValidationError(
                    code="unsafe_csv_formula",
                    field=target,
                    message="Formula-like text is not accepted in imported operation data.",
                    value=raw,
                )
            )
            continue

        if target in _METRIC_FIELDS:
            value = _parse_non_negative_decimal(raw, field_name=target, errors=errors)
            if value is not None:
                normalized[target] = value
        elif target == "revenue_amount":
            value = _parse_non_negative_decimal(raw, field_name=target, errors=errors)
            if value is not None:
                normalized[target] = value
        elif target == "extra_metrics":
            _merge_extra_metrics_json(raw, extra_metrics, errors)
        elif target.startswith("extra_metrics."):
            metric_name = target.partition(".")[2]
            value = _parse_non_negative_decimal(raw, field_name=target, errors=errors)
            if value is not None:
                extra_metrics[metric_name] = value
        else:
            normalized[target] = raw

    platform = _optional_text(normalized.get("platform"))
    if not platform:
        errors.append(
            RowValidationError(
                code="missing_platform",
                field="platform",
                message="platform is required.",
            )
        )
    else:
        try:
            normalized["platform"] = normalize_platform(platform)
        except ValueError as exc:
            errors.append(
                RowValidationError(
                    code="invalid_platform",
                    field="platform",
                    message=str(exc),
                    value=platform,
                )
            )

    content_id = _optional_text(normalized.get("external_content_id"))
    if content_id:
        normalized["external_content_id"] = content_id
    external_url = _optional_text(normalized.get("external_url"))
    if external_url:
        try:
            normalized["external_url"] = normalize_external_url(external_url)
        except ValueError as exc:
            errors.append(
                RowValidationError(
                    code="invalid_external_url",
                    field="external_url",
                    message=str(exc),
                    value=external_url,
                )
            )

    amount = normalized.get("revenue_amount")
    currency = _optional_text(normalized.get("currency"))
    if amount is not None and not currency:
        errors.append(
            RowValidationError(
                code="missing_currency",
                field="currency",
                message="currency is required when revenue_amount is present.",
            )
        )
    if currency:
        normalized_currency = _CURRENCY_ALIASES.get(currency.casefold(), currency.upper())
        if not _CURRENCY_RE.fullmatch(normalized_currency):
            errors.append(
                RowValidationError(
                    code="invalid_currency",
                    field="currency",
                    message="currency must be a three-letter ISO-style code such as CNY.",
                    value=currency,
                )
            )
        else:
            normalized["currency"] = normalized_currency

    if extra_metrics:
        normalized["extra_metrics"] = dict(sorted(extra_metrics.items()))
    return normalized, errors


def _parse_non_negative_decimal(
    raw: str,
    *,
    field_name: str,
    errors: list[RowValidationError],
) -> Decimal | None:
    candidate = raw.replace(",", "").strip()
    try:
        value = Decimal(candidate)
    except InvalidOperation:
        errors.append(
            RowValidationError(
                code="invalid_number",
                field=field_name,
                message=f"{field_name} must be a finite number.",
                value=raw,
            )
        )
        return None
    if not value.is_finite():
        errors.append(
            RowValidationError(
                code="invalid_number",
                field=field_name,
                message=f"{field_name} must be a finite number.",
                value=raw,
            )
        )
        return None
    if value < 0:
        errors.append(
            RowValidationError(
                code="negative_metric",
                field=field_name,
                message=f"{field_name} must not be negative.",
                value=raw,
            )
        )
        return None
    return value.normalize() if value else Decimal("0")


def _merge_extra_metrics_json(
    raw: str,
    destination: dict[str, Decimal],
    errors: list[RowValidationError],
) -> None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        errors.append(
            RowValidationError(
                code="invalid_extra_metrics",
                field="extra_metrics",
                message="extra_metrics must be a JSON object containing non-negative numbers.",
                value=raw,
            )
        )
        return
    if not isinstance(payload, dict):
        errors.append(
            RowValidationError(
                code="invalid_extra_metrics",
                field="extra_metrics",
                message="extra_metrics must be a JSON object containing non-negative numbers.",
                value=raw,
            )
        )
        return
    for raw_name, raw_value in payload.items():
        name = str(raw_name).strip()
        if not _is_valid_extra_metric_name(name):
            errors.append(
                RowValidationError(
                    code="invalid_extra_metric_name",
                    field="extra_metrics",
                    message=f"Invalid extra metric name: {name!r}.",
                    value=name,
                )
            )
            continue
        value = _parse_non_negative_decimal(
            str(raw_value),
            field_name=f"extra_metrics.{name}",
            errors=errors,
        )
        if value is not None:
            destination[name] = value


def _detect_import_kind(
    data: bytes,
    *,
    filename: str | None,
    media_type: str | None,
) -> ImportKind:
    suffix = ""
    if filename:
        normalized_name = filename.lower().strip()
        suffix = "." + normalized_name.rpartition(".")[2] if "." in normalized_name else ""
    normalized_media_type = (media_type or "").partition(";")[0].strip().lower()
    if suffix == ".xls":
        raise UnsupportedOperationImportTypeError(
            "Legacy .xls files are not supported; export the workbook as .xlsx or CSV."
        )
    if suffix == ".xlsx" or normalized_media_type == XLSX_MEDIA_TYPE:
        return "xlsx"
    if suffix == ".csv" or normalized_media_type in CSV_MEDIA_TYPES:
        return "csv"
    if data.startswith(b"PK\x03\x04"):
        return "xlsx"
    raise UnsupportedOperationImportTypeError(
        "Only CSV and .xlsx operation-data files are supported."
    )


def _parse_csv(data: bytes, *, max_rows: int, max_columns: int) -> _ParsedTable:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidOperationImportError("CSV files must use UTF-8 encoding.") from exc
    if "\x00" in text:
        raise InvalidOperationImportError("The CSV file contains NUL bytes.")
    try:
        reader = csv.reader(StringIO(text, newline=""), strict=True)
        records = list(reader)
    except csv.Error as exc:
        raise InvalidOperationImportError(f"The CSV file is malformed: {exc}.") from exc
    if not records:
        raise EmptyOperationImportError("The CSV file contains no rows.")
    if len(records[0]) > max_columns:
        raise InvalidOperationImportError(f"The CSV file exceeds the {max_columns}-column limit.")

    headers = tuple(cell.strip() for cell in records[0])
    _validate_headers(headers)
    rows: list[tuple[int, tuple[str, ...], frozenset[int]]] = []
    for row_number, record in enumerate(records[1:], start=2):
        if len(rows) >= max_rows:
            raise InvalidOperationImportError(f"The import exceeds the {max_rows}-row limit.")
        if len(record) > max_columns:
            raise InvalidOperationImportError(
                f"CSV row {row_number} exceeds the {max_columns}-column limit."
            )
        if len(record) > len(headers):
            raise InvalidOperationImportError(
                f"CSV row {row_number} contains more values than the header row."
            )
        values = tuple(_validate_cell(value, row_number=row_number) for value in record)
        if not any(value.strip() for value in values):
            continue
        padded = values + ("",) * (len(headers) - len(values))
        rows.append((row_number, padded, frozenset()))
    return _ParsedTable(
        import_kind="csv",
        sheet_name=None,
        headers=headers,
        rows=tuple(rows),
        warnings=(),
    )


def _parse_xlsx(data: bytes, *, max_rows: int, max_columns: int) -> _ParsedTable:
    archive = _open_validated_xlsx(data)
    with archive:
        shared_strings = _read_shared_strings(archive)
        sheet_name, sheet_path, extra_sheet_count = _first_worksheet(archive)
        rows = _read_worksheet(
            archive,
            sheet_path,
            shared_strings=shared_strings,
            max_rows=max_rows + 1,
            max_columns=max_columns,
        )
    if not rows:
        raise EmptyOperationImportError("The XLSX worksheet contains no rows.")

    header_row_number, header_values, _ = rows[0]
    headers = tuple(value.strip() for value in header_values)
    _validate_headers(headers)
    parsed_rows: list[tuple[int, tuple[str, ...], frozenset[int]]] = []
    for row_number, values, formulas in rows[1:]:
        if not any(value.strip() for value in values):
            continue
        padded = values + ("",) * (len(headers) - len(values))
        if len(padded) > len(headers):
            raise InvalidOperationImportError(
                f"XLSX row {row_number} contains values beyond the header columns."
            )
        parsed_rows.append((row_number, padded, formulas))
    if len(parsed_rows) > max_rows:
        raise InvalidOperationImportError(f"The import exceeds the {max_rows}-row limit.")

    warnings: tuple[str, ...] = ()
    if extra_sheet_count:
        warnings = (
            f"Only worksheet {sheet_name!r} was imported; "
            f"{extra_sheet_count} additional worksheet(s) were ignored.",
        )
    if header_row_number != 1:
        warnings += (f"The XLSX header was read from worksheet row {header_row_number}.",)
    return _ParsedTable(
        import_kind="xlsx",
        sheet_name=sheet_name,
        headers=headers,
        rows=tuple(parsed_rows),
        warnings=warnings,
    )


def _open_validated_xlsx(data: bytes) -> ZipFile:
    try:
        archive = ZipFile(BytesIO(data))
    except (BadZipFile, OSError, ValueError) as exc:
        raise InvalidOperationImportError("The XLSX file is corrupt or invalid.") from exc

    try:
        members = archive.infolist()
        if len(members) > MAX_XLSX_MEMBERS:
            raise UnsafeOperationArchiveError("The XLSX archive contains too many entries.")
        names: set[str] = set()
        total_uncompressed = 0
        for member in members:
            path = _validate_archive_member(member.filename)
            if path in names:
                raise UnsafeOperationArchiveError(f"Duplicate XLSX archive path: {path}.")
            names.add(path)
            if member.flag_bits & 0x1:
                raise UnsafeOperationArchiveError(
                    "Encrypted XLSX archive entries are not supported."
                )
            unix_mode = member.external_attr >> 16
            if unix_mode & 0o170000 == 0o120000:
                raise UnsafeOperationArchiveError(
                    "Symbolic links are not allowed in XLSX archives."
                )
            total_uncompressed += member.file_size
            if total_uncompressed > MAX_XLSX_UNCOMPRESSED_BYTES:
                raise UnsafeOperationArchiveError(
                    "The XLSX archive expands beyond the safe processing limit."
                )
            if (
                member.file_size > 1_000_000
                and member.compress_size > 0
                and member.file_size / member.compress_size > MAX_XLSX_COMPRESSION_RATIO
            ):
                raise UnsafeOperationArchiveError(
                    "The XLSX archive contains an unsafe compression ratio."
                )
        required = {"[Content_Types].xml", "xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
        if not required.issubset(names):
            raise InvalidOperationImportError("The uploaded archive is not a valid XLSX workbook.")
        return archive
    except Exception:
        archive.close()
        raise


def _validate_archive_member(raw_path: str) -> str:
    if not raw_path or "\\" in raw_path or "\x00" in raw_path:
        raise UnsafeOperationArchiveError("The XLSX archive contains an unsafe path.")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise UnsafeOperationArchiveError(f"Unsafe XLSX archive path: {raw_path!r}.")
    if path.parts and ":" in path.parts[0]:
        raise UnsafeOperationArchiveError(f"Unsafe XLSX archive path: {raw_path!r}.")
    return path.as_posix()


def _read_shared_strings(archive: ZipFile) -> tuple[str, ...]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return ()
    root = _parse_xml(archive.read("xl/sharedStrings.xml"), "shared strings")
    values: list[str] = []
    for item in root.findall(f"{{{_XLSX_MAIN_NS}}}si"):
        values.append("".join(node.text or "" for node in item.iter(f"{{{_XLSX_MAIN_NS}}}t")))
    return tuple(values)


def _first_worksheet(archive: ZipFile) -> tuple[str, str, int]:
    workbook = _parse_xml(archive.read("xl/workbook.xml"), "workbook")
    relationships = _parse_xml(
        archive.read("xl/_rels/workbook.xml.rels"),
        "workbook relationships",
    )
    targets = {
        relationship.attrib.get("Id", ""): relationship.attrib.get("Target", "")
        for relationship in relationships.findall(f"{{{_PACKAGE_REL_NS}}}Relationship")
        if relationship.attrib.get("Type", "").endswith("/worksheet")
    }
    sheets = workbook.findall(f".//{{{_XLSX_MAIN_NS}}}sheet")
    if not sheets:
        raise InvalidOperationImportError("The XLSX workbook contains no worksheets.")
    first = sheets[0]
    relation_id = first.attrib.get(f"{{{_OFFICE_REL_NS}}}id", "")
    target = targets.get(relation_id)
    if not target:
        raise InvalidOperationImportError("The first XLSX worksheet relationship is invalid.")
    normalized_target = target.lstrip("/")
    if not normalized_target.startswith("xl/"):
        normalized_target = f"xl/{normalized_target}"
    sheet_path = _validate_archive_member(normalized_target)
    if sheet_path not in archive.namelist():
        raise InvalidOperationImportError("The first XLSX worksheet is missing.")
    return first.attrib.get("name", "Sheet1"), sheet_path, len(sheets) - 1


def _read_worksheet(
    archive: ZipFile,
    sheet_path: str,
    *,
    shared_strings: tuple[str, ...],
    max_rows: int,
    max_columns: int,
) -> list[tuple[int, tuple[str, ...], frozenset[int]]]:
    root = _parse_xml(archive.read(sheet_path), "worksheet")
    output: list[tuple[int, tuple[str, ...], frozenset[int]]] = []
    for row_element in root.findall(f".//{{{_XLSX_MAIN_NS}}}row"):
        if len(output) >= max_rows:
            raise InvalidOperationImportError(f"The import exceeds the {max_rows - 1}-row limit.")
        row_number = int(row_element.attrib.get("r", len(output) + 1))
        cells: dict[int, str] = {}
        formulas: set[int] = set()
        for cell in row_element.findall(f"{{{_XLSX_MAIN_NS}}}c"):
            reference = cell.attrib.get("r", "")
            match = _CELL_REFERENCE_RE.fullmatch(reference)
            if not match:
                raise InvalidOperationImportError(
                    f"The XLSX worksheet contains an invalid cell reference: {reference!r}."
                )
            column_index = _column_index(match.group(1))
            if column_index >= max_columns:
                raise InvalidOperationImportError(
                    f"The XLSX worksheet exceeds the {max_columns}-column limit."
                )
            if cell.find(f"{{{_XLSX_MAIN_NS}}}f") is not None:
                formulas.add(column_index)
            value = _xlsx_cell_text(cell, shared_strings)
            cells[column_index] = _validate_cell(value, row_number=row_number)
        if not cells:
            continue
        width = max(cells) + 1
        output.append(
            (
                row_number,
                tuple(cells.get(index, "") for index in range(width)),
                frozenset(formulas),
            )
        )
    return output


def _xlsx_cell_text(cell: ElementTree.Element, shared_strings: tuple[str, ...]) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        inline = cell.find(f"{{{_XLSX_MAIN_NS}}}is")
        if inline is None:
            return ""
        return "".join(node.text or "" for node in inline.iter(f"{{{_XLSX_MAIN_NS}}}t"))
    value_node = cell.find(f"{{{_XLSX_MAIN_NS}}}v")
    value = "" if value_node is None or value_node.text is None else value_node.text
    if cell_type == "s":
        try:
            return shared_strings[int(value)]
        except (ValueError, IndexError) as exc:
            raise InvalidOperationImportError(
                "The XLSX worksheet references an invalid shared string."
            ) from exc
    if cell_type == "b":
        return "true" if value == "1" else "false"
    return value


def _parse_xml(data: bytes, description: str) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise InvalidOperationImportError(f"The XLSX {description} XML is invalid.") from exc


def _column_index(letters: str) -> int:
    result = 0
    for character in letters:
        result = result * 26 + (ord(character) - ord("A") + 1)
    return result - 1


def _validate_headers(headers: Sequence[str]) -> None:
    if not headers or not any(header for header in headers):
        raise InvalidFieldMappingError("The import file must contain a header row.")
    if any(not header for header in headers):
        raise InvalidFieldMappingError("Every imported column must have a non-empty header.")
    if len({_header_key(header) for header in headers}) != len(headers):
        raise InvalidFieldMappingError("Imported column headers must be unique ignoring case.")


def _validate_cell(value: str, *, row_number: int) -> str:
    if "\x00" in value:
        raise InvalidOperationImportError(f"Row {row_number} contains a NUL byte.")
    if len(value) > MAX_CELL_CHARACTERS:
        raise InvalidOperationImportError(
            f"Row {row_number} contains a cell longer than {MAX_CELL_CHARACTERS} characters."
        )
    return value


def _is_mapping_target(value: str) -> bool:
    return value in CANONICAL_FIELDS or value.startswith("extra_metrics.")


def _normalize_mapping_target(value: str) -> str:
    if value in CANONICAL_FIELDS:
        return value
    if value.startswith("extra_metrics."):
        metric_name = value.partition(".")[2]
        if _is_valid_extra_metric_name(metric_name):
            return f"extra_metrics.{metric_name}"
    raise InvalidFieldMappingError(f"Unsupported canonical field: {value!r}.")


def _header_key(value: str) -> str:
    return value.strip().casefold().replace(" ", "_")


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_plain_number(value: str) -> bool:
    try:
        return Decimal(value.replace(",", "")).is_finite()
    except InvalidOperation:
        return False


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        normalized = value.normalize() if value else Decimal("0")
        return format(normalized, "f")
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _validate_positive_limit(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer.")


def _is_valid_extra_metric_name(value: str) -> bool:
    if not value or len(value) > 64 or value[0].isdigit():
        return False
    return all(character.isalnum() or character in "_.-" for character in value)
