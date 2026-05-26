"""
Refresh KardexComplianceCache rows (UIF + SISGEN collectors).
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from django.contrib.auth.models import AbstractBaseUser
from notaria import models

from compliance.models import KardexComplianceCache
from compliance.services.kardex_meta import kardex_meta_from_model, parse_kardex_date
from compliance.services.payload import build_payload, counts_from_payload
from compliance.services.sisgen_collector import collect_sisgen_issues
from compliance.services.uif_collector import collect_uif_issues

logger = logging.getLogger(__name__)

EXCLUDED_TIPOKAR = (2, 5)


class ComplianceRefreshService:
    def refresh_kardex(
        self,
        kardex: str,
        *,
        user: Optional[AbstractBaseUser] = None,
    ) -> Optional[KardexComplianceCache]:
        key = str(kardex or "").strip()
        if not key:
            return None

        kardex_row = models.Kardex.objects.filter(kardex=key).first()
        if not kardex_row:
            return None

        uif_block = collect_uif_issues(key)
        sisgen_block = collect_sisgen_issues(key)
        payload = build_payload(
            kardex=key,
            idkardex=str(kardex_row.idkardex or ""),
            idtipkar=kardex_row.idtipkar,
            kardex_meta=kardex_meta_from_model(kardex_row),
            uif_block=uif_block,
            sisgen_block=sisgen_block,
        )
        counts = counts_from_payload(payload)

        cache, _ = KardexComplianceCache.objects.update_or_create(
            kardex=key,
            defaults={
                "idkardex": str(kardex_row.idkardex or ""),
                "idtipkar": kardex_row.idtipkar,
                "fechaescritura": parse_kardex_date(kardex_row.fechaescritura),
                "payload": payload,
                "updated_by": user if user and user.is_authenticated else None,
                **counts,
            },
        )
        return cache

    def refresh_date_range(
        self,
        start_date: date,
        end_date: date,
        *,
        user: Optional[AbstractBaseUser] = None,
    ) -> Dict[str, Any]:
        kardex_list = list(
            models.Kardex.objects.filter(fechaescritura__range=[start_date, end_date])
            .exclude(idtipkar__in=EXCLUDED_TIPOKAR)
            .values_list("kardex", flat=True)
            .distinct()
        )
        refreshed = 0
        skipped = 0
        errors: List[str] = []
        for kardex in kardex_list:
            if not kardex:
                skipped += 1
                continue
            try:
                row = self.refresh_kardex(kardex, user=user)
                if row:
                    refreshed += 1
                else:
                    skipped += 1
            except Exception as exc:
                logger.exception("Compliance refresh failed for %s", kardex)
                errors.append(f"{kardex}: {exc}")
        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_kardex": len(kardex_list),
            "refreshed": refreshed,
            "skipped": skipped,
            "failed": len(errors),
            "failures": errors[:50],
        }
