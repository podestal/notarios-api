"""
PHP vs Python UIF parity — export and compare plane / dashboard for one period.

Golden layout (under ``app/uif/tests/fixtures/php_parity/<period>/``):

- ``manifest.json`` — initialDate, finalDate, reportPolicy
- ``plane.php.txt`` — legacy RoClass ``generateFileRo`` export (CRLF)
- ``errors.php.json`` — optional full ``lista_errores`` from PHP dashboard
- ``summary.php.json`` — optional PHP dashboard summary counts
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from uif.services.dashboard_service import UifDashboardService
from uif.services.plane_rows import PLANE_BODY_LINE_LENGTH, PLANE_HEADER_LINE_LENGTH
from uif.services.report_data import get_uif_report_data, parse_report_dates
from uif.services.reports import UifReportService

FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "php_parity"


@dataclass(frozen=True)
class ParityManifest:
    initial_date: str
    final_date: str
    report_policy: str = "all"
    description: str = ""

    @classmethod
    def load(cls, path: Path) -> "ParityManifest":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            initial_date=str(data["initialDate"]),
            final_date=str(data["finalDate"]),
            report_policy=str(data.get("reportPolicy") or "all"),
            description=str(data.get("description") or ""),
        )


def resolve_fixture_dir(period: Optional[str] = None) -> Optional[Path]:
    """Return fixture dir if manifest + plane.php.txt exist."""
    if period:
        candidate = FIXTURES_ROOT / period
        if (candidate / "manifest.json").is_file() and (candidate / "plane.php.txt").is_file():
            return candidate
        return None

    if not FIXTURES_ROOT.is_dir():
        return None
    for child in sorted(FIXTURES_ROOT.iterdir()):
        if child.is_dir() and (child / "manifest.json").is_file() and (child / "plane.php.txt").is_file():
            return child
    return None


def normalize_plane_text(text: str) -> List[str]:
    """Normalize line endings; drop trailing empty lines."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def build_python_parity_bundle(
    initial_date: str,
    final_date: str,
    report_policy: str = "all",
) -> Dict[str, Any]:
    start_date, end_date = parse_report_dates(initial_date, final_date)
    data = get_uif_report_data(
        start_date, end_date, initial_date, final_date, report_policy=report_policy
    )
    plane_response = UifReportService().generate_plane_report(data, initial_date, final_date)
    plane_text = plane_response.content.decode("utf-8")

    dashboard = UifDashboardService().run(
        start_date, end_date, initial_date, final_date, include_valid=False
    )
    return {
        "manifest": {
            "initialDate": initial_date,
            "finalDate": final_date,
            "reportPolicy": report_policy,
        },
        "plane": plane_text,
        "plane_lines": normalize_plane_text(plane_text),
        "errors": dashboard.get("lista_errores") or [],
        "summary": dashboard.get("summary") or {},
        "report_record_count": len(data.get("lista_kardex_report_active") or []),
    }


def error_signature(error: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        error.get("kardex"),
        str(error.get("codacto") or ""),
        int(error.get("fieldNumber") or 0),
        error.get("error_type"),
        error.get("idContratante"),
        str(error.get("categoryCorrect") or ""),
    )


def normalize_errors_for_compare(errors: Iterable[Dict[str, Any]]) -> List[Tuple[Any, ...]]:
    return sorted(error_signature(e) for e in errors)


def compare_plane_lines(
    python_lines: List[str], php_lines: List[str]
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "match": python_lines == php_lines,
        "python_line_count": len(python_lines),
        "php_line_count": len(php_lines),
        "first_diff_index": None,
        "python_sample": None,
        "php_sample": None,
    }
    if python_lines == php_lines:
        return result

    max_len = max(len(python_lines), len(php_lines))
    for idx in range(max_len):
        py_line = python_lines[idx] if idx < len(python_lines) else None
        php_line = php_lines[idx] if idx < len(php_lines) else None
        if py_line != php_line:
            result["first_diff_index"] = idx
            result["python_sample"] = py_line
            result["php_sample"] = php_line
            if idx == 0:
                result["python_header_len"] = len(py_line or "")
                result["php_header_len"] = len(php_line or "")
            else:
                result["python_body_len"] = len(py_line or "")
                result["php_body_len"] = len(php_line or "")
            break
    return result


def validate_plane_structure(lines: List[str]) -> List[str]:
    issues: List[str] = []
    if not lines:
        issues.append("plane file is empty")
        return issues
    if len(lines[0]) != PLANE_HEADER_LINE_LENGTH:
        issues.append(
            f"header line length {len(lines[0])} != {PLANE_HEADER_LINE_LENGTH}"
        )
    for idx, line in enumerate(lines[1:], start=2):
        if len(line) != PLANE_BODY_LINE_LENGTH:
            issues.append(
                f"body line {idx} length {len(line)} != {PLANE_BODY_LINE_LENGTH}"
            )
            if len(issues) >= 5:
                issues.append("…")
                break
    return issues


def write_python_export(fixture_dir: Path, bundle: Dict[str, Any]) -> None:
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / "plane.python.txt").write_text(bundle["plane"], encoding="utf-8")
    (fixture_dir / "errors.python.json").write_text(
        json.dumps(bundle["errors"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (fixture_dir / "summary.python.json").write_text(
        json.dumps(bundle["summary"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
