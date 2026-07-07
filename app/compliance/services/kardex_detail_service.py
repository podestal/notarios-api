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


def _build_escrituracion_pending_detail(kardex_row: models.Kardex) -> Dict[str, Any]:
    meta = escrituracion_pending_meta(kardex_row)
    return {
        "kardex": kardex_row.kardex,
        "idkardex": str(kardex_row.idkardex or ""),
        "idtipkar": kardex_row.idtipkar,
        "numescritura": kardex_row.numescritura,
        "fechaingreso": kardex_row.fechaingreso,
        "fechaescritura": kardex_row.fechaescritura,
        "validated_at": None,
        "source": "escrituracion_pending",
        "has_errors": False,
        "counts": {"sisgen": 0, "uif": 0, "pdt": 0, "total": 0},
        "errors": {
            SOURCE_SISGEN: {"errores": [], "personas": [], "observaciones": []},
            SOURCE_UIF: {"errors": [], "observations": []},
            SOURCE_PDT: empty_pdt_block(),
        },
        "kardex_meta": kardex_meta_from_model(kardex_row),
        "summary": {"has_errors": False, "total_errors": 0},
        **meta,
    }


def _build_sisgen_sent_detail(kardex_row: models.Kardex) -> Dict[str, Any]:
    meta = sisgen_sent_meta(kardex_row)
    return {
        "kardex": kardex_row.kardex,
        "idkardex": str(kardex_row.idkardex or ""),
        "idtipkar": kardex_row.idtipkar,
        "numescritura": kardex_row.numescritura,
        "fechaingreso": kardex_row.fechaingreso,
        "fechaescritura": kardex_row.fechaescritura,
        "validated_at": None,
        "source": "sisgen_sent",
        "has_errors": False,
        "counts": {"sisgen": 0, "uif": 0, "pdt": 0, "total": 0},
        "errors": {
            SOURCE_SISGEN: {"errores": [], "personas": [], "observaciones": []},
            SOURCE_UIF: {"errors": [], "observations": []},
            SOURCE_PDT: empty_pdt_block(),
        },
        "kardex_meta": kardex_meta_from_model(kardex_row),
        "summary": {"has_errors": False, "total_errors": 0},
        **meta,
    }


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

        if is_kardex_sent_to_sisgen(kardex_row.estado_sisgen):
            return _build_sisgen_sent_detail(kardex_row)

        if not has_escrituracion_info(kardex_row):
            return _build_escrituracion_pending_detail(kardex_row)

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

        if is_kardex_sent_to_sisgen(kardex_row.estado_sisgen):
            return _build_sisgen_sent_detail(kardex_row)

        if not has_escrituracion_info(kardex_row):
            return _build_escrituracion_pending_detail(kardex_row)

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
