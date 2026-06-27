"""
Monthly compliance error counts grouped by kardex preparer (idusuario).

Default: single-pass live validation (no cache).
Optional cache=true reads KardexComplianceCache when pre-warmed.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from django.contrib.auth import get_user_model
from django.utils import timezone

from notaria import models

from compliance.models import KardexComplianceCache
from compliance.services.bulk_collector import bulk_collect_compliance_error_counts
from compliance.services.payload import sisgen_errores_count_from_payload
from compliance.services.refresh_service import EXCLUDED_TIPOKAR

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


def _user_display_name(user) -> str:
    if user is None:
        return ""
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return name or getattr(user, "username", "") or ""


def _load_month_kardex_and_counts(
    *,
    year: Optional[int] = None,
    month: Optional[int] = None,
    use_cache: bool = False,
    idusuario: Optional[int] = None,
) -> Dict[str, Any]:
    y, m, start, end = parse_year_month(year, month)
    start_s = start.isoformat()
    end_s = end.isoformat()

    qs = (
        models.Kardex.objects.filter(fechaingreso__gte=start_s, fechaingreso__lte=end_s)
        .exclude(idtipkar__in=EXCLUDED_TIPOKAR)
        .exclude(kardex__isnull=True)
        .exclude(kardex="")
    )
    if idusuario is not None:
        qs = qs.filter(idusuario=idusuario)

    kardex_models = list(qs)
    kardex_rows = [
        {
            "kardex": str(k.kardex).strip(),
            "idkardex": k.idkardex,
            "idusuario": k.idusuario,
            "numescritura": k.numescritura,
            "fechaingreso": k.fechaingreso,
            "fechaescritura": k.fechaescritura,
            "idtipkar": k.idtipkar,
        }
        for k in kardex_models
        if k.kardex and str(k.kardex).strip()
    ]
    kardex_keys = [r["kardex"] for r in kardex_rows]

    if use_cache:
        cache_by_kardex = {
            row.kardex: row
            for row in KardexComplianceCache.objects.filter(kardex__in=kardex_keys).only(
                "kardex", "uif_error_count", "payload"
            )
        }
        counts_by_kardex = {}
        for k in kardex_keys:
            cache_row = cache_by_kardex.get(k)
            if cache_row:
                counts_by_kardex[k] = {
                    "sisgen": sisgen_errores_count_from_payload(cache_row.payload),
                    "uif": int(cache_row.uif_error_count or 0),
                }
            else:
                counts_by_kardex[k] = {"sisgen": 0, "uif": 0}
        source_meta = {
            "source": "kardex_compliance_cache",
            "cached": len(cache_by_kardex),
            "missing": len(kardex_keys) - len(cache_by_kardex),
            "note": (
                "Reading KardexComplianceCache. "
                "POST /compliance/refresh/ to populate missing rows. "
                "Omit cache=true for live validation."
            ),
        }
    else:
        counts_by_kardex = bulk_collect_compliance_error_counts(kardex_models)
        source_meta = {
            "source": "live_validation",
            "kardex_validated": len(kardex_keys),
            "note": (
                "Single-pass live validation (batch DB prefetch, parallel SISGEN/UIF). "
                "Add cache=true to read precomputed KardexComplianceCache instead."
            ),
        }

    user_ids = {
        int(r["idusuario"])
        for r in kardex_rows
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
            "date_field": "fechaingreso",
        },
        "kardex_rows": kardex_rows,
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
    ) -> Dict[str, Any]:
        data = _load_month_kardex_and_counts(
            year=year, month=month, use_cache=use_cache
        )
        kardex_rows = data["kardex_rows"]
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

        for row in kardex_rows:
            uid = int(row.get("idusuario") or 0)
            k = str(row.get("kardex") or "").strip()
            if not k:
                continue

            item = counts_by_kardex.get(k) or {"sisgen": 0, "uif": 0}
            counts = _kardex_counts_item(item)
            sisgen_n = counts["sisgen"]
            uif_n = counts["uif"]
            pdt_n = counts["pdt"]
            item_total = counts["total"]

            bucket = stats[uid]
            bucket["total_kardex"] += 1
            bucket["counts"]["sisgen"] += sisgen_n
            bucket["counts"]["uif"] += uif_n
            bucket["counts"]["pdt"] += pdt_n
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
            "total_kardex": len(kardex_rows),
            "total_users": len(users_out),
            "kardex_with_errors": sum(u["kardex_with_errors"] for u in users_out),
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
        idusuario: Optional[int] = None,
        errors_only: bool = True,
    ) -> Dict[str, Any]:
        """Per-user kardex list with error counts (no error payloads)."""
        data = _load_month_kardex_and_counts(
            year=year,
            month=month,
            use_cache=use_cache,
            idusuario=idusuario,
        )
        kardex_rows = data["kardex_rows"]
        counts_by_kardex = data["counts_by_kardex"]
        users_by_id = data["users_by_id"]

        by_user: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for row in kardex_rows:
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
                    "kardex_count": len(kardex_list),
                    "counts": {
                        "sisgen": sum(i["counts"]["sisgen"] for i in kardex_list),
                        "uif": sum(i["counts"]["uif"] for i in kardex_list),
                        "pdt": 0,
                        "total": sum(i["counts"]["total"] for i in kardex_list),
                    },
                    "kardex": kardex_list,
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
            "total_kardex": len(all_kardex),
            "counts": {
                "sisgen": sum(i["counts"]["sisgen"] for i in all_kardex),
                "uif": sum(i["counts"]["uif"] for i in all_kardex),
                "pdt": 0,
                "total": sum(i["counts"]["total"] for i in all_kardex),
            },
            "pdt_note": "PDT not included yet",
        }

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
