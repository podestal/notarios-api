"""Live or cached per-kardex compliance error detail."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from notaria import models

from compliance.models import KardexComplianceCache
from compliance.services.kardex_meta import kardex_meta_from_model
from compliance.services.payload import (
    SOURCE_PDT,
    SOURCE_SISGEN,
    SOURCE_UIF,
    build_payload,
    build_sisgen_block,
    empty_pdt_block,
    filter_payload_sources,
    serialize_kardex_errors_detail,
)
from compliance.services.sisgen_collector import collect_sisgen_issues
from compliance.services.uif_collector import collect_uif_issues
from compliance.services.escrituracion_filter import (
    escrituracion_pending_meta,
    has_escrituracion_info,
)
from compliance.services.sisgen_sent_filter import is_kardex_sent_to_sisgen, sisgen_sent_meta
from compliance.services.access import kardex_owned_by_user


class KardexNotFoundError(LookupError):
    pass


class ComplianceCacheNotFoundError(LookupError):
    pass


def _empty_sisgen_block() -> Dict[str, Any]:
    return build_sisgen_block(errores=[], observaciones=[], personas=[])


class KardexComplianceDetailService:
    def _build_live_detail(
        self,
        kardex_row: models.Kardex,
        *,
        source_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Always collect UIF (same engine as UIF report).

        SISGEN is skipped when already sent or pending escrituración — those flags
        no longer wipe UIF errors.
        """
        key = str(kardex_row.kardex or "").strip()
        skip_sisgen = is_kardex_sent_to_sisgen(
            kardex_row.estado_sisgen
        ) or not has_escrituracion_info(kardex_row)

        uif_block = collect_uif_issues(key)
        if skip_sisgen:
            sisgen_block = _empty_sisgen_block()
            if is_kardex_sent_to_sisgen(kardex_row.estado_sisgen):
                source = "live_validation_sisgen_sent"
            else:
                source = "live_validation_escrituracion_pending"
        else:
            sisgen_block = collect_sisgen_issues(key)
            source = "live_validation"

        payload = build_payload(
            kardex=key,
            idkardex=str(kardex_row.idkardex or ""),
            idtipkar=kardex_row.idtipkar,
            kardex_meta=kardex_meta_from_model(kardex_row),
            uif_block=uif_block,
            sisgen_block=sisgen_block,
            validated_at=datetime.utcnow(),
        )
        detail = serialize_kardex_errors_detail(
            kardex_row=kardex_row,
            payload=filter_payload_sources(payload, source_filter),
            source=source,
            source_filter=source_filter,
        )
        if is_kardex_sent_to_sisgen(kardex_row.estado_sisgen):
            detail.update(sisgen_sent_meta(kardex_row))
        if not has_escrituracion_info(kardex_row):
            detail.update(escrituracion_pending_meta(kardex_row))
        return detail

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

        return self._build_live_detail(kardex_row, source_filter=source_filter)

    def build_detail_for_user(
        self,
        user,
        kardex: str,
        *,
        use_cache: bool = False,
        source_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Like ``build_detail`` but only for kardex owned by ``user`` (preparer)."""
        key = str(kardex or "").strip()
        if not key:
            raise KardexNotFoundError("Kardex is required")

        kardex_row = kardex_owned_by_user(kardex=key, user=user)
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

        return self._build_live_detail(kardex_row, source_filter=source_filter)
