"""
Ops / admin endpoints for escrituración reservations and correlative counters.

Restricted to staff or superuser (``IsStaffOrSuperuser``).
"""

from __future__ import annotations

from django.db import transaction
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import IsStaffOrSuperuser
from notaria.models import Kardex
from notaria.pagination import KardexPagination
from signatum import correlatives, models, serializers


class AdminReservationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Manage notarization reservations.

    Filters: ``status``, ``idtipkar``, ``kardex``, ``held_by``.
    Paginated with ``page`` / ``page_size`` (KardexPagination).
    """

    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]
    serializer_class = serializers.NotarizationReservationSerializer
    pagination_class = KardexPagination
    queryset = models.NotarizationReservation.objects.select_related("held_by").all()

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        status_q = (params.get("status") or "").strip().upper()
        if status_q:
            qs = qs.filter(status=status_q)

        idtipkar = params.get("idtipkar")
        if idtipkar not in (None, ""):
            try:
                qs = qs.filter(idtipkar=int(idtipkar))
            except (TypeError, ValueError):
                raise ValidationError({"idtipkar": "Must be an integer."})

        kardex = (params.get("kardex") or "").strip()
        if kardex:
            qs = qs.filter(kardex__icontains=kardex)

        held_by = params.get("held_by")
        if held_by not in (None, ""):
            try:
                qs = qs.filter(held_by_id=int(held_by))
            except (TypeError, ValueError):
                raise ValidationError({"held_by": "Must be a user id integer."})

        return qs

    @action(detail=True, methods=["post"], url_path="release")
    def release(self, request, pk=None):
        """
        Force-release a pending reservation lock (EX or CA).

        Body: ``{ "status": "EX"|"CA", "reason": "optional" }``
        """
        ser = serializers.AdminReleaseReservationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        with transaction.atomic():
            reservation = (
                models.NotarizationReservation.objects.select_for_update()
                .filter(pk=pk)
                .first()
            )
            if reservation is None:
                raise NotFound("Reservation not found.")

            if reservation.status != models.NotarizationReservation.Status.PENDING:
                raise ValidationError(
                    {
                        "status": (
                            f"Only pending (PE) reservations can be released; "
                            f"current status is {reservation.status}."
                        )
                    }
                )

            new_status = ser.validated_data["status"]
            reservation.status = new_status
            reservation.save(update_fields=["status"])

        data = self.get_serializer(reservation).data
        data["admin_action"] = {
            "action": "release",
            "reason": ser.validated_data.get("reason") or "",
            "by_user_id": request.user.id,
        }
        return Response(data)


class AdminCorrelativeCounterViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """List / inspect / set correlative counters (year + idtipkar)."""

    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]
    serializer_class = serializers.CorrelativeCounterSerializer
    queryset = models.CorrelativeCounter.objects.all()
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        year = params.get("year")
        if year not in (None, ""):
            try:
                qs = qs.filter(year=int(year))
            except (TypeError, ValueError):
                raise ValidationError({"year": "Must be an integer."})

        idtipkar = params.get("idtipkar")
        if idtipkar not in (None, ""):
            try:
                qs = qs.filter(idtipkar=int(idtipkar))
            except (TypeError, ValueError):
                raise ValidationError({"idtipkar": "Must be an integer."})

        return qs

    @action(detail=False, methods=["get"], url_path="by-key")
    def by_key(self, request):
        """
        GET ``?year=2026&idtipkar=3`` — fetch the counter for that key
        (creates/seeds it if missing, without allocating a number).
        """
        try:
            year = int(request.query_params.get("year") or correlatives.correlative_year_today())
            idtipkar = int(request.query_params["idtipkar"])
        except (KeyError, TypeError, ValueError):
            raise ValidationError(
                {"detail": "Query params year (optional) and idtipkar (required) must be integers."}
            )

        with transaction.atomic():
            from signatum.allocation import get_locked_counter

            counter = get_locked_counter(year=year, idtipkar=idtipkar)

        return Response(self.get_serializer(counter).data)

    @action(detail=False, methods=["post"], url_path="set")
    def set_counter(self, request):
        """
        Create or overwrite counter values for ``year`` + ``idtipkar``.

        Body example::
            {
              "year": 2026,
              "idtipkar": 3,
              "next_num_escritura": 140,
              "last_folio": "202 VTA"
            }
        """
        ser = serializers.AdminSetCounterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        with transaction.atomic():
            counter, _created = models.CorrelativeCounter.objects.select_for_update().get_or_create(
                year=data["year"],
                idtipkar=data["idtipkar"],
                defaults={
                    "next_num_escritura": data.get("next_num_escritura", 1),
                    "next_num_minuta": data.get("next_num_minuta", 1),
                    "last_folio": data.get("last_folio", ""),
                },
            )
            updated = []
            if "next_num_escritura" in data:
                counter.next_num_escritura = data["next_num_escritura"]
                updated.append("next_num_escritura")
            if "next_num_minuta" in data:
                counter.next_num_minuta = data["next_num_minuta"]
                updated.append("next_num_minuta")
            if "last_folio" in data:
                counter.last_folio = data["last_folio"]
                updated.append("last_folio")
            if updated:
                counter.save(update_fields=[*updated, "updated_at"])

        out = self.get_serializer(counter).data
        out["admin_action"] = {
            "action": "set",
            "by_user_id": request.user.id,
            "updated_fields": updated,
        }
        return Response(out)

    def partial_update(self, request, *args, **kwargs):
        """PATCH ``/admin/counters/{id}/`` — update next numbers / last_folio."""
        ser = serializers.AdminPatchCounterSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if not data:
            raise ValidationError({"detail": "No fields to update."})

        with transaction.atomic():
            counter = (
                models.CorrelativeCounter.objects.select_for_update()
                .filter(pk=kwargs["pk"])
                .first()
            )
            if counter is None:
                raise NotFound("Counter not found.")

            for field, value in data.items():
                setattr(counter, field, value)
            counter.save(update_fields=[*data.keys(), "updated_at"])

        out = self.get_serializer(counter).data
        out["admin_action"] = {
            "action": "patch",
            "by_user_id": request.user.id,
            "updated_fields": list(data.keys()),
        }
        return Response(out)


class AdminNotarizationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Inspect and correct committed notarizations (optionally sync kardex)."""

    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]
    serializer_class = serializers.NotarizationSerializer
    queryset = models.Notarization.objects.select_related(
        "created_by", "source_reservation"
    ).all()
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        idtipkar = params.get("idtipkar")
        if idtipkar not in (None, ""):
            try:
                qs = qs.filter(idtipkar=int(idtipkar))
            except (TypeError, ValueError):
                raise ValidationError({"idtipkar": "Must be an integer."})

        kardex = (params.get("kardex") or "").strip()
        if kardex:
            qs = qs.filter(kardex__icontains=kardex)

        num_escritura = (params.get("num_escritura") or "").strip()
        if num_escritura:
            qs = qs.filter(num_escritura=num_escritura)

        year = params.get("year")
        if year not in (None, ""):
            try:
                qs = qs.filter(created_at__year=int(year))
            except (TypeError, ValueError):
                raise ValidationError({"year": "Must be an integer."})

        return qs

    def partial_update(self, request, *args, **kwargs):
        """
        PATCH committed correlatives.

        Body may include ``sync_kardex`` (default true) and ``sync_counter_folio``.
        """
        ser = serializers.AdminPatchNotarizationSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        sync_kardex = data.pop("sync_kardex", True)
        sync_counter_folio = data.pop("sync_counter_folio", False)
        if not data:
            raise ValidationError({"detail": "No correlative fields to update."})

        kardex_sync = None
        with transaction.atomic():
            notarization = (
                models.Notarization.objects.select_for_update()
                .filter(pk=kwargs["pk"])
                .first()
            )
            if notarization is None:
                raise NotFound("Notarization not found.")

            for field, value in data.items():
                setattr(notarization, field, value)
            notarization.save(update_fields=list(data.keys()))

            if sync_kardex:
                kardex_row = Kardex.objects.filter(kardex=notarization.kardex).first()
                if kardex_row is None:
                    raise ValidationError(
                        {"sync_kardex": f"Kardex {notarization.kardex} not found."}
                    )
                mapping = {
                    "num_escritura": "numescritura",
                    "num_minuta": "numminuta",
                    "folio_ini": "folioini",
                    "folio_fin": "foliofin",
                    "papel_ini": "papelini",
                    "papel_fin": "papelfin",
                    "fecha_escritura": "fechaescritura",
                    "fecha_conclusion": "fechaconclusion",
                }
                k_updated = []
                for src, dest in mapping.items():
                    if src in data:
                        setattr(kardex_row, dest, data[src])
                        k_updated.append(dest)
                if k_updated:
                    kardex_row.save(update_fields=k_updated)
                kardex_sync = {"kardex": notarization.kardex, "updated_fields": k_updated}

            if sync_counter_folio:
                year = (
                    notarization.created_at.year
                    if notarization.created_at
                    else correlatives.correlative_year_today()
                )
                from signatum.allocation import advance_folio_on_commit

                advance_folio_on_commit(
                    year=year,
                    idtipkar=notarization.idtipkar,
                    folio_fin=notarization.folio_fin or notarization.folio_ini,
                )

        out = self.get_serializer(notarization).data
        out["admin_action"] = {
            "action": "patch",
            "by_user_id": request.user.id,
            "updated_fields": list(data.keys()),
            "kardex_sync": kardex_sync,
            "sync_counter_folio": sync_counter_folio,
        }
        return Response(out)
