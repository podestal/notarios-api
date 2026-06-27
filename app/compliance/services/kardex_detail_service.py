"""Live or cached per-kardex compliance error detail."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from notaria import models

from compliance.models import KardexComplianceCache
from compliance.services.kardex_meta import kardex_meta_from_model
from compliance.services.payload import (
    build_payload,
    filter_payload_sources,
    serialize_kardex_errors_detail,
)
from compliance.services.sisgen_collector import collect_sisgen_issues
from compliance.services.uif_collector import collect_uif_issues


class KardexNotFoundError(LookupError):
    pass


class ComplianceCacheNotFoundError(LookupError):
    pass


class KardexComplianceDetailService:
    def build_detail(
        self,
        kardex: str,
        *,
        use_cache: bool = False,
        source_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        key = str(kardex or "").strip()
        if not key:
            raise KardexNotFoundError("Kardex is required")

        kardex_row = models.Kardex.objects.filter(kardex=key).first()
        if not kardex_row:
            raise KardexNotFoundError(f"Kardex not found: {key}")

        if use_cache:
            cache_row = KardexComplianceCache.objects.filter(kardex=key).first()
            if not cache_row:
                raise ComplianceCacheNotFoundError(
                    f"No compliance cache for {key}. "
                    "POST /compliance/refresh/ or omit cache=true for live validation."
                )
            payload = cache_row.payload or {}
            validated_at = payload.get("validated_at") or cache_row.updated_at.isoformat()
            return serialize_kardex_errors_detail(
                kardex_row=kardex_row,
                payload=filter_payload_sources(payload, source_filter),
                source="kardex_compliance_cache",
                validated_at=validated_at,
                source_filter=source_filter,
            )

        uif_block = collect_uif_issues(key)
        sisgen_block = collect_sisgen_issues(key)
        payload = build_payload(
            kardex=key,
            idkardex=str(kardex_row.idkardex or ""),
            idtipkar=kardex_row.idtipkar,
            kardex_meta=kardex_meta_from_model(kardex_row),
            uif_block=uif_block,
            sisgen_block=sisgen_block,
            validated_at=datetime.utcnow(),
        )
        return serialize_kardex_errors_detail(
            kardex_row=kardex_row,
            payload=filter_payload_sources(payload, source_filter),
            source="live_validation",
            source_filter=source_filter,
        )
