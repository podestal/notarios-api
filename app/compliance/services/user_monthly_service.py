"""
Monthly compliance error counts grouped by kardex preparer (idusuario).

UIF counts: same pipeline as the UIF report (``UifDashboardService``).
SISGEN counts: live/cache validation; sisgen-sent / pending escritura skip SISGEN only.

Default: hybrid cache for SISGEN when available; UIF always from dashboard.
Optional cache=true (SISGEN from cache only) or live=true (force SISGEN live).
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional, Set, Tuple

from django.contrib.auth import get_user_model
from django.utils import timezone

from notaria import models

from compliance.models import KardexComplianceCache
from compliance.services.bulk_collector import bulk_collect_compliance_error_counts
from compliance.services.payload import sisgen_errores_count_from_payload
from compliance.services.refresh_service import EXCLUDED_TIPOKAR
from compliance.services.escrituracion_filter import partition_kardex_by_escrituracion
from compliance.services.sisgen_sent_filter import partition_kardex_by_sisgen_sent
from compliance.services.uif_parity import count_uif_errors_by_kardex

User = get_user_model()


def parse_year_month(
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> Tuple[int, int, date, date]:
    """Default period = current calendar month on the server."""
    today = timezone.localdate()
    y = int(year) if year is not None else today.year
    m = int(month) if month is not None else today.month
    if m < 1 or m > 12:
        raise ValueError("month must be between 1 and 12")
    last_day = calendar.monthrange(y, m)[1]
    start = date(y, m, 1)
    end = date(y, m, last_day)
    return y, m, start, end


def shift_year_month(year: int, month: int, delta_months: int) -> Tuple[int, int]:
    """Shift a calendar month by ``delta_months`` (negative = past)."""
    idx = year * 12 + (month - 1) + delta_months
    return idx // 12, (idx % 12) + 1


def months_window(
    year: Optional[int] = None,
    month: Optional[int] = None,
    *,
    months_back: int = 2,
) -> List[Tuple[int, int]]:
    """
    Focus month + previous ``months_back`` months, newest first.

    Default: current/requested month, previous, and the one before (3 total).
    """
    y, m, _, _ = parse_year_month(year, month)
    return [shift_year_month(y, m, -i) for i in range(months_back + 1)]


def _user_display_name(user) -> str:
    if user is None:
        return ""
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return name or getattr(user, "username", "") or ""


def _kardex_row_from_model(k: models.Kardex) -> Dict[str, Any]:
    return {
        "kardex": str(k.kardex).strip(),
        "idkardex": k.idkardex,
        "idusuario": k.idusuario,
        "numescritura": k.numescritura,
        "fechaingreso": k.fechaingreso,
        "fechaescritura": k.fechaescritura,
        "idtipkar": k.idtipkar,
        "estado_sisgen": k.estado_sisgen,
    }


EXCLUDED_TIPOKAR = (2, 5)

KARDEX_MONTH_FIELDS = (
    "kardex",
    "idkardex",
    "idusuario",
    "numescritura",
    "fechaingreso",
    "fechaescritura",
    "idtipkar",
    "estado_sisgen",
    "codactos",
)


def _counts_from_cache_row(cache_row: KardexComplianceCache) -> Dict[str, int]:
    return {
        "sisgen": sisgen_errores_count_from_payload(cache_row.payload),
        "uif": int(cache_row.uif_error_count or 0),
    }


def _load_cache_counts_by_kardex(
    kardex_keys: List[str],
) -> Dict[str, KardexComplianceCache]:
    if not kardex_keys:
        return {}
    return {
        row.kardex: row
        for row in KardexComplianceCache.objects.filter(kardex__in=kardex_keys).only(
            "kardex", "uif_error_count", "payload"
        )
    }


def _sisgen_counts_for_models(
    kardex_models: List[models.Kardex],
    *,
    use_cache: bool,
    force_live: bool,
) -> Tuple[Dict[str, int], Dict[str, Any]]:
    """SISGEN-only counts; UIF is filled later from the dashboard pipeline."""
    keys = [str(k.kardex).strip() for k in kardex_models if k.kardex and str(k.kardex).strip()]
    empty_meta = {
        "sisgen_source": "none",
        "sisgen_cached": 0,
        "sisgen_live_validated": 0,
    }
    if not keys:
        return {}, empty_meta

    if use_cache:
        cache_by_kardex = _load_cache_counts_by_kardex(keys)
        out = {}
        for k in keys:
            cache_row = cache_by_kardex.get(k)
            out[k] = int(_counts_from_cache_row(cache_row)["sisgen"]) if cache_row else 0
        return out, {
            "sisgen_source": "kardex_compliance_cache",
            "sisgen_cached": len(cache_by_kardex),
            "sisgen_live_validated": 0,
        }

    if force_live:
        live = bulk_collect_compliance_error_counts(
            kardex_models, include_uif=False, include_sisgen=True
        )
        return (
            {k: int((live.get(k) or {}).get("sisgen") or 0) for k in keys},
            {
                "sisgen_source": "live_validation",
                "sisgen_cached": 0,
                "sisgen_live_validated": len(keys),
            },
        )

    cache_by_kardex = _load_cache_counts_by_kardex(keys)
    out: Dict[str, int] = {}
    missing_models: List[models.Kardex] = []
    for row in kardex_models:
        k = str(row.kardex or "").strip()
        if not k:
            continue
        cache_row = cache_by_kardex.get(k)
        if cache_row:
            out[k] = int(_counts_from_cache_row(cache_row)["sisgen"])
        else:
            missing_models.append(row)

    if missing_models:
        live = bulk_collect_compliance_error_counts(
            missing_models, include_uif=False, include_sisgen=True
        )
        for row in missing_models:
            k = str(row.kardex or "").strip()
            out[k] = int((live.get(k) or {}).get("sisgen") or 0)

    cached_n = len(cache_by_kardex)
    missing_n = len(missing_models)
    if cached_n and missing_n:
        source = "hybrid"
    elif cached_n:
        source = "kardex_compliance_cache"
    else:
        source = "live_validation"
    return out, {
        "sisgen_source": source,
        "sisgen_cached": cached_n,
        "sisgen_live_validated": missing_n,
    }


def _load_month_kardex_and_counts(
    *,
    year: Optional[int] = None,
    month: Optional[int] = None,
    use_cache: bool = False,
    force_live: bool = False,
    idusuario: Optional[int] = None,
) -> Dict[str, Any]:
    y, m, start, end = parse_year_month(year, month)
    start_s = start.isoformat()
    end_s = end.isoformat()

    # Same date field as UIF report / RoLoadDataService.
    qs = (
        models.Kardex.objects.filter(fechaescritura__range=[start, end])
        .exclude(idtipkar__in=EXCLUDED_TIPOKAR)
        .exclude(kardex__isnull=True)
        .exclude(kardex="")
        .only(*KARDEX_MONTH_FIELDS)
    )
    if idusuario is not None:
        qs = qs.filter(idusuario=idusuario)

    kardex_models_all = list(qs)
    by_key: Dict[str, models.Kardex] = {
        str(k.kardex).strip(): k
        for k in kardex_models_all
        if k.kardex and str(k.kardex).strip()
    }

    # UIF source of truth (includes complementary tipo C + threshold).
    uif_by_kardex = count_uif_errors_by_kardex(start, end, idusuario=idusuario)

    # Pull in complementary / out-of-month kardex that still have UIF errors.
    missing_uif_keys = [k for k in uif_by_kardex.keys() if k not in by_key]
    if missing_uif_keys:
        extra_qs = models.Kardex.objects.filter(kardex__in=missing_uif_keys).only(
            *KARDEX_MONTH_FIELDS
        )
        if idusuario is not None:
            extra_qs = extra_qs.filter(idusuario=idusuario)
        for row in extra_qs:
            key = str(row.kardex or "").strip()
            if key and key not in by_key:
                by_key[key] = row
                kardex_models_all.append(row)

    sisgen_models, excluded_sisgen_sent = partition_kardex_by_sisgen_sent(kardex_models_all)
    sisgen_models, excluded_pending_escrituracion = partition_kardex_by_escrituracion(
        sisgen_models
    )
    sisgen_eligible_keys: Set[str] = {
        str(k.kardex).strip()
        for k in sisgen_models
        if k.kardex and str(k.kardex).strip()
    }

    sisgen_by_kardex, sisgen_meta = _sisgen_counts_for_models(
        sisgen_models,
        use_cache=use_cache,
        force_live=force_live,
    )

    all_kardex_rows = [
        _kardex_row_from_model(k)
        for k in kardex_models_all
        if k.kardex and str(k.kardex).strip()
    ]
    # Every kardex can carry UIF errors; SISGEN is zeroed when excluded.
    eligible_kardex_rows = list(all_kardex_rows)
    kardex_keys = [r["kardex"] for r in eligible_kardex_rows]

    counts_by_kardex: Dict[str, Dict[str, int]] = {}
    for k in kardex_keys:
        counts_by_kardex[k] = {
            "uif": int(uif_by_kardex.get(k) or 0),
            "sisgen": int(sisgen_by_kardex.get(k) or 0)
            if k in sisgen_eligible_keys
            else 0,
        }
    # UIF-only keys that somehow lacked a row model still contribute to totals.
    for k, uif_n in uif_by_kardex.items():
        if k not in counts_by_kardex:
            counts_by_kardex[k] = {"uif": int(uif_n), "sisgen": 0}

    exclusion_meta = {
        "excluded_sisgen_sent": len(excluded_sisgen_sent),
        "excluded_pending_escrituracion": len(excluded_pending_escrituracion),
        "sisgen_sent_note": (
            "Kardex con estado_sisgen Enviado (1) u Observado (2) no cuentan errores "
            "SISGEN; los errores UIF sí se reportan (misma regla que el reporte UIF)."
        ),
        "escrituracion_note": (
            "Kardex sin numescritura no se validan para SISGEN; "
            "los errores UIF sí se reportan (misma regla que el reporte UIF)."
        ),
        "uif_source": "uif_dashboard",
        "uif_note": (
            "UIF counts from UifDashboardService (fechaescritura, threshold, "
            "complementary tipo C) — same engine as the UIF report."
        ),
        **sisgen_meta,
    }

    sisgen_source = sisgen_meta.get("sisgen_source") or "none"
    if sisgen_source == "hybrid":
        source = "hybrid"
        note = (
            "UIF from dashboard; SISGEN hybrid (cache + live). "
            "POST /compliance/refresh/ to warm SISGEN cache."
        )
    elif sisgen_source == "kardex_compliance_cache":
        source = "kardex_compliance_cache"
        note = "UIF from dashboard; SISGEN from KardexComplianceCache."
    elif sisgen_source == "live_validation":
        source = "live_validation"
        note = "UIF from dashboard; SISGEN live validation."
    else:
        source = "uif_dashboard"
        note = "UIF from dashboard; no SISGEN-eligible kardex this period."

    source_meta = {
        "source": source,
        "cached": sisgen_meta.get("sisgen_cached", 0),
        "missing": sisgen_meta.get("sisgen_live_validated", 0),
        "live_validated": sisgen_meta.get("sisgen_live_validated", 0),
        "kardex_validated": len(sisgen_eligible_keys),
        "uif_kardex_with_errors": sum(1 for n in uif_by_kardex.values() if n > 0),
        "uif_total_errors": sum(uif_by_kardex.values()),
        **exclusion_meta,
        "note": note,
    }

    user_ids = {
        int(r["idusuario"])
        for r in all_kardex_rows
        if r.get("idusuario") is not None
    }
    users_by_id = {
        u.idusuario: u
        for u in User.objects.filter(idusuario__in=user_ids)
    }

    return {
        "year": y,
        "month": m,
        "period": {
            "start": start_s,
            "end": end_s,
            "date_field": "fechaescritura",
        },
        "all_kardex_rows": all_kardex_rows,
        "eligible_kardex_rows": eligible_kardex_rows,
        "kardex_rows": eligible_kardex_rows,
        "counts_by_kardex": counts_by_kardex,
        "source_meta": source_meta,
        "users_by_id": users_by_id,
    }


def _kardex_counts_item(counts: Dict[str, int]) -> Dict[str, int]:
    sisgen_n = int(counts.get("sisgen") or 0)
    uif_n = int(counts.get("uif") or 0)
    pdt_n = int(counts.get("pdt") or 0)
    return {
        "sisgen": sisgen_n,
        "uif": uif_n,
        "pdt": pdt_n,
        "total": sisgen_n + uif_n + pdt_n,
    }


class ComplianceUserMonthlyService:
    def build_report(
        self,
        *,
        year: Optional[int] = None,
        month: Optional[int] = None,
        use_cache: bool = False,
        force_live: bool = False,
    ) -> Dict[str, Any]:
        data = _load_month_kardex_and_counts(
            year=year,
            month=month,
            use_cache=use_cache,
            force_live=force_live,
        )
        all_kardex_rows = data["all_kardex_rows"]
        eligible_kardex_rows = data["eligible_kardex_rows"]
        counts_by_kardex = data["counts_by_kardex"]
        users_by_id = data["users_by_id"]

        stats: Dict[int, Dict[str, Any]] = defaultdict(
            lambda: {
                "total_kardex": 0,
                "kardex_with_errors": 0,
                "counts": {
                    "sisgen": 0,
                    "uif": 0,
                    "pdt": 0,
                    "total": 0,
                },
            }
        )

        for row in all_kardex_rows:
            uid = int(row.get("idusuario") or 0)
            stats[uid]["total_kardex"] += 1

        for row in eligible_kardex_rows:
            uid = int(row.get("idusuario") or 0)
            k = str(row.get("kardex") or "").strip()
            if not k:
                continue

            item = counts_by_kardex.get(k) or {"sisgen": 0, "uif": 0}
            counts = _kardex_counts_item(item)
            item_total = counts["total"]

            bucket = stats[uid]
            bucket["counts"]["sisgen"] += counts["sisgen"]
            bucket["counts"]["uif"] += counts["uif"]
            bucket["counts"]["pdt"] += counts["pdt"]
            bucket["counts"]["total"] += item_total
            if item_total > 0:
                bucket["kardex_with_errors"] += 1

        users_out: List[Dict[str, Any]] = []
        for uid, bucket in stats.items():
            user = users_by_id.get(uid)
            total_k = bucket["total_kardex"]
            with_err = bucket["kardex_with_errors"]
            users_out.append(
                {
                    "idusuario": uid,
                    "name": _user_display_name(user),
                    "username": getattr(user, "username", "") if user else "",
                    "total_kardex": total_k,
                    "kardex_with_errors": with_err,
                    "kardex_clean": total_k - with_err,
                    "error_rate": round(with_err / total_k, 4) if total_k else 0.0,
                    "counts": dict(bucket["counts"]),
                }
            )

        users_out.sort(
            key=lambda u: (
                -u["kardex_with_errors"],
                -u["counts"]["total"],
                -u["total_kardex"],
                u["idusuario"],
            )
        )

        summary = {
            "total_kardex": len(all_kardex_rows),
            "kardex_checked_for_errors": len(eligible_kardex_rows),
            "total_users": len(users_out),
            "kardex_with_errors": sum(u["kardex_with_errors"] for u in users_out),
            "excluded_sisgen_sent": data["source_meta"].get("excluded_sisgen_sent", 0),
            "excluded_pending_escrituracion": data["source_meta"].get(
                "excluded_pending_escrituracion", 0
            ),
            "counts": {
                "sisgen": sum(u["counts"]["sisgen"] for u in users_out),
                "uif": sum(u["counts"]["uif"] for u in users_out),
                "pdt": 0,
                "total": sum(u["counts"]["total"] for u in users_out),
            },
            "pdt_note": "PDT not included yet",
        }

        return {
            "year": data["year"],
            "month": data["month"],
            "period": data["period"],
            "source": data["source_meta"],
            "summary": summary,
            "users": users_out,
        }

    def build_user_kardex_report(
        self,
        *,
        year: Optional[int] = None,
        month: Optional[int] = None,
        use_cache: bool = False,
        force_live: bool = False,
        idusuario: Optional[int] = None,
        errors_only: bool = True,
    ) -> Dict[str, Any]:
        """Per-user kardex list with error counts (no error payloads)."""
        data = _load_month_kardex_and_counts(
            year=year,
            month=month,
            use_cache=use_cache,
            force_live=force_live,
            idusuario=idusuario,
        )
        all_kardex_rows = data["all_kardex_rows"]
        eligible_kardex_rows = data["eligible_kardex_rows"]
        counts_by_kardex = data["counts_by_kardex"]
        users_by_id = data["users_by_id"]

        totals_by_user: Dict[int, int] = defaultdict(int)
        for row in all_kardex_rows:
            totals_by_user[int(row.get("idusuario") or 0)] += 1

        by_user: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for row in eligible_kardex_rows:
            k = str(row.get("kardex") or "").strip()
            if not k:
                continue
            counts = _kardex_counts_item(counts_by_kardex.get(k) or {})
            if errors_only and counts["total"] <= 0:
                continue
            uid = int(row.get("idusuario") or 0)
            by_user[uid].append(
                {
                    "kardex": k,
                    "idkardex": row.get("idkardex"),
                    "numescritura": row.get("numescritura"),
                    "fechaingreso": row.get("fechaingreso"),
                    "fechaescritura": row.get("fechaescritura"),
                    "idtipkar": row.get("idtipkar"),
                    "counts": counts,
                }
            )

        users_out: List[Dict[str, Any]] = []
        for uid, kardex_list in by_user.items():
            if errors_only and not kardex_list:
                continue
            user = users_by_id.get(uid)
            total_k = totals_by_user.get(uid, 0)
            with_err = len(kardex_list) if errors_only else sum(
                1 for item in kardex_list if item["counts"]["total"] > 0
            )
            kardex_list.sort(
                key=lambda item: (
                    -item["counts"]["total"],
                    -item["counts"]["sisgen"],
                    -item["counts"]["uif"],
                    item["kardex"],
                )
            )
            users_out.append(
                {
                    "idusuario": uid,
                    "name": _user_display_name(user),
                    "username": getattr(user, "username", "") if user else "",
                    "total_kardex": total_k,
                    "kardex_with_errors": with_err,
                    "kardex_count": len(kardex_list),
                    "error_rate": round(with_err / total_k, 4) if total_k else 0.0,
                    "counts": {
                        "sisgen": sum(i["counts"]["sisgen"] for i in kardex_list),
                        "uif": sum(i["counts"]["uif"] for i in kardex_list),
                        "pdt": 0,
                        "total": sum(i["counts"]["total"] for i in kardex_list),
                    },
                    "kardex": kardex_list,
                }
            )

        # Users with only SISGEN-sent kardex (no error rows) still appear when errors_only=false
        if not errors_only:
            for uid, total_k in totals_by_user.items():
                if uid in by_user:
                    continue
                user = users_by_id.get(uid)
                users_out.append(
                    {
                        "idusuario": uid,
                        "name": _user_display_name(user),
                        "username": getattr(user, "username", "") if user else "",
                        "total_kardex": total_k,
                        "kardex_with_errors": 0,
                        "kardex_count": 0,
                        "error_rate": 0.0,
                        "counts": {"sisgen": 0, "uif": 0, "pdt": 0, "total": 0},
                        "kardex": [],
                    }
                )

        users_out.sort(
            key=lambda u: (
                -u["kardex_count"],
                -u["counts"]["total"],
                u["idusuario"],
            )
        )

        all_kardex = [item for u in users_out for item in u["kardex"]]
        summary = {
            "total_users": len(users_out),
            "total_kardex": len(all_kardex_rows),
            "kardex_with_errors": len(all_kardex),
            "kardex_checked_for_errors": len(eligible_kardex_rows),
            "excluded_sisgen_sent": data["source_meta"].get("excluded_sisgen_sent", 0),
            "excluded_pending_escrituracion": data["source_meta"].get(
                "excluded_pending_escrituracion", 0
            ),
            "counts": {
                "sisgen": sum(i["counts"]["sisgen"] for i in all_kardex),
                "uif": sum(i["counts"]["uif"] for i in all_kardex),
                "pdt": 0,
                "total": sum(i["counts"]["total"] for i in all_kardex),
            },
            "pdt_note": "PDT not included yet",
        }

        if idusuario is not None and not users_out and totals_by_user.get(idusuario, 0) > 0:
            user = users_by_id.get(idusuario)
            users_out.append(
                {
                    "idusuario": idusuario,
                    "name": _user_display_name(user),
                    "username": getattr(user, "username", "") if user else "",
                    "total_kardex": totals_by_user[idusuario],
                    "kardex_with_errors": 0,
                    "kardex_count": 0,
                    "error_rate": 0.0,
                    "counts": {"sisgen": 0, "uif": 0, "pdt": 0, "total": 0},
                    "kardex": [],
                }
            )

        result: Dict[str, Any] = {
            "year": data["year"],
            "month": data["month"],
            "period": data["period"],
            "source": data["source_meta"],
            "errors_only": errors_only,
            "summary": summary,
            "users": users_out,
        }
        if idusuario is not None:
            result["idusuario"] = idusuario
        return result

    def build_my_kardex_summary(
        self,
        *,
        year: Optional[int] = None,
        month: Optional[int] = None,
        use_cache: bool = False,
        force_live: bool = False,
        idusuario: int,
        errors_only: bool = True,
        months_back: int = 1,
    ) -> Dict[str, Any]:
        """
        Counts-only summary for the focus month + previous ``months_back`` months.

        Default ``months_back=1`` → current/requested month and the past month.
        Kardex rows are not included — fetch them via ``build_user_kardex_report``
        for a single year/month.
        """
        window = months_window(year, month, months_back=months_back)
        focus_y, focus_m = window[0]
        months_out: List[Dict[str, Any]] = []

        for y, m in window:
            report = self.build_user_kardex_report(
                year=y,
                month=m,
                use_cache=use_cache,
                force_live=force_live,
                idusuario=idusuario,
                errors_only=errors_only,
            )
            if report["users"]:
                block = report["users"][0]
                months_out.append(
                    {
                        "year": y,
                        "month": m,
                        "total_kardex": block["total_kardex"],
                        "kardex_with_errors": block["kardex_with_errors"],
                        "counts": block["counts"],
                    }
                )
            else:
                months_out.append(
                    {
                        "year": y,
                        "month": m,
                        "total_kardex": 0,
                        "kardex_with_errors": 0,
                        "counts": {"sisgen": 0, "uif": 0, "pdt": 0, "total": 0},
                    }
                )

        return {
            "year": focus_y,
            "month": focus_m,
            "idusuario": idusuario,
            "months": months_out,
        }

    # Back-compat alias
    build_my_kardex_rolling_report = build_my_kardex_summary