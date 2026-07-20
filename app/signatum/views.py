from datetime import timedelta
import re

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response



from . import allocation, correlatives, models, serializers


class NotarizationViewSet(viewsets.ModelViewSet):
    queryset = models.Notarization.objects.all()
    serializer_class = serializers.NotarizationSerializer


class SerieNotarialViewSet(viewsets.ModelViewSet):
    queryset = models.SerieNotarial.objects.all()
    serializer_class = serializers.SerieNotarialSerializer

    def list(self, request, *args, **kwargs):
        """Return series notarial; optional query ``idtipkar`` filters by tipo de kardex."""
        qs = self.get_queryset()
        idtipkar = request.query_params.get("idtipkar")
        if idtipkar:
            qs = qs.filter(idtipkar=idtipkar, activo=True)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)


class NotarizationReservationViewSet(viewsets.ModelViewSet):
    """
    On create: expire stale pendings (>5 min) for the same idtipkar, then enforce
    lock only within that tipo. Correlatives chain is per calendar year + idtipkar.
    """

    queryset = models.NotarizationReservation.objects.all()
    serializer_class = serializers.NotarizationReservationSerializer

    RESERVATION_BLOCK_MINUTES = 5

    def get_serializer_class(self):
        if self.action == "create":
            return serializers.CreateNotarizationReservationSerializer
        return serializers.NotarizationReservationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        output = serializers.NotarizationReservationSerializer(
            serializer.instance,
            context=self.get_serializer_context(),
        )
        if getattr(self, "_reservation_reused", False):
            return Response(output.data, status=status.HTTP_200_OK)
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)

    def _release_stale_pending_on_create(self, idtipkar: int) -> None:
        """Mark PE rows older than 5 minutes as EX, only for this tipo de kardex."""
        cutoff = timezone.now() - timedelta(minutes=self.RESERVATION_BLOCK_MINUTES)
        models.NotarizationReservation.objects.filter(
            idtipkar=idtipkar,
            status=models.NotarizationReservation.Status.PENDING,
            created_at__lt=cutoff,
        ).update(status=models.NotarizationReservation.Status.EXPIRED)

    def _active_pending_reservation(self, idtipkar: int):
        return (
            models.NotarizationReservation.objects.filter(
                idtipkar=idtipkar,
                status=models.NotarizationReservation.Status.PENDING,
            )
            .select_related("held_by")
            .order_by("-id")
            .first()
        )

    def _active_pending_reservation_for_user_scope(self, *, user, idtipkar: int, kardex: str):
        return (
            models.NotarizationReservation.objects.filter(
                idtipkar=idtipkar,
                kardex=kardex,
                held_by=user,
                status=models.NotarizationReservation.Status.PENDING,
            )
            .select_related("held_by")
            .order_by("-id")
            .first()
        )

    def _last_notarization_any_year(self, idtipkar: int):
        return (
            models.Notarization.objects.filter(idtipkar=idtipkar)
            .order_by("-id")
            .first()
        )

    def _paper_num_side(self, paper_value: str):
        """
        Return (number, side) where side 0=recto, 1=VTA.
        Accepts '123', '123 VTA', '123V', '123VTA'.
        """
        s = (paper_value or "").strip().upper()
        if not s:
            return None
        m = re.match(r"^(\d+)\s*(VTA|V)?$", s)
        if not m:
            return None
        num = int(m.group(1))
        side = 1 if (m.group(2) in {"VTA", "V"}) else 0
        return (num, side)

    def _paper_to_string(self, number: int, side: int) -> str:
        return f"{number} VTA" if side == 1 else str(number)

    def _paper_next(self, number: int, side: int):
        if side == 0:
            return (number, 1)
        return (number + 1, 0)

    def _active_series_ranges(self, idtipkar: int):
        """
        For reservations, only the latest active purchased range applies (not a merge of all).
        Latest = newest created_at, then highest id.
        """
        serie = (
            models.SerieNotarial.objects.filter(idtipkar=idtipkar, activo=True)
            .order_by("-created_at", "-id")
            .first()
        )
        if not serie:
            return []
        ini = self._paper_num_side(serie.papel_ini)
        fin = self._paper_num_side(serie.papel_fin)
        if not ini or not fin:
            return []
        start_num, end_num = ini[0], fin[0]
        if end_num < start_num:
            return []
        return [(start_num, end_num)]

    def _proposed_papel_from_series(self, idtipkar: int):
        """
        Propose next paper from configured active series.
        If no active series or no remaining pages, return empty strings.
        """
        ranges = self._active_series_ranges(idtipkar)
        if not ranges:
            return ("", "")

        last_any = self._last_notarization_any_year(idtipkar)
        last_paper = self._paper_num_side(
            (last_any.papel_fin or last_any.papel_ini or "") if last_any else ""
        )

        # First ever use or last value not parseable: start at first active range start.
        if last_paper is None:
            start_num = ranges[0][0]
            proposed = self._paper_to_string(start_num, 0)
            return (proposed, proposed)

        cand_num, cand_side = self._paper_next(last_paper[0], last_paper[1])

        # Keep candidate if still inside any active range.
        for start_num, end_num in ranges:
            if start_num <= cand_num <= end_num:
                proposed = self._paper_to_string(cand_num, cand_side)
                return (proposed, proposed)

        # Otherwise jump to the next range start after the last used number.
        for start_num, end_num in ranges:
            if start_num > last_paper[0]:
                proposed = self._paper_to_string(start_num, 0)
                return (proposed, proposed)

        # Exhausted all configured ranges.
        return ("", "")

    def _build_reservation_fields(
        self, *, kardex: str, idtipkar: int, year: int, user
    ):
        allocated = allocation.allocate_correlatives(year=year, idtipkar=idtipkar)
        papel_ini, papel_fin = self._proposed_papel_from_series(idtipkar)
        return {
            "idtipkar": idtipkar,
            "kardex": kardex,
            "fecha_conclusion": "",
            "folio_ini": allocated.folio,
            "folio_fin": allocated.folio,
            "papel_ini": papel_ini,
            "papel_fin": papel_fin,
            "num_minuta": allocated.num_minuta,
            "num_escritura": allocated.num_escritura,
            "fecha_escritura": correlatives.today_iso(),
            "status": models.NotarizationReservation.Status.PENDING,
            "held_by": user,
        }

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        self._reservation_reused = False
        if not user.is_authenticated:
            raise PermissionDenied("Authentication required to reserve.")

        idtipkar = serializer.validated_data["idtipkar"]
        kardex = serializer.validated_data["kardex"].strip()
        if not kardex:
            raise ValidationError({"kardex": "This field may not be blank."})

        self._release_stale_pending_on_create(idtipkar)

        # Idempotent behavior for refresh/retry:
        # if same user already has an active reservation for the same kardex + tipo,
        # return that row instead of raising an error.
        existing_for_same_scope = self._active_pending_reservation_for_user_scope(
            user=user,
            idtipkar=idtipkar,
            kardex=kardex,
        )
        if existing_for_same_scope is not None:
            serializer.instance = existing_for_same_scope
            self._reservation_reused = True
            return

        # Lock any active PE row for this tipo so concurrent creates serialize.
        active = (
            models.NotarizationReservation.objects.select_for_update()
            .filter(
                idtipkar=idtipkar,
                status=models.NotarizationReservation.Status.PENDING,
            )
            .select_related("held_by")
            .order_by("-id")
            .first()
        )
        if active is not None:
            if active.held_by_id != user.id:
                raise ValidationError(
                    {
                        "detail": (
                            "Another user has an active notarization reservation "
                            "for this tipo de kardex. Try again after they finish "
                            "or after 5 minutes."
                        )
                    }
                )
            raise ValidationError(
                {
                    "detail": (
                        "You already have an active reservation for this tipo de kardex. "
                        "Complete or cancel it before creating another."
                    )
                }
            )

        year = correlatives.correlative_year_today()
        payload = self._build_reservation_fields(
            kardex=kardex, idtipkar=idtipkar, year=year, user=user
        )
        serializer.save(**payload)
