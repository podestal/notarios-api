from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from . import correlatives, models, serializers


class NotarizationViewSet(viewsets.ModelViewSet):
    queryset = models.Notarization.objects.all()
    serializer_class = serializers.NotarizationSerializer


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

    def _last_notarization_for_year(self, year: int, idtipkar: int):
        return (
            models.Notarization.objects.filter(
                created_at__year=year,
                idtipkar=idtipkar,
            )
            .order_by("-id")
            .first()
        )

    def _build_reservation_fields(
        self, *, kardex: str, idtipkar: int, year: int, user
    ):
        last = self._last_notarization_for_year(year, idtipkar)
        if last is None:
            one = "1"
            return {
                "idtipkar": idtipkar,
                "kardex": kardex,
                "fecha_conclusion": "",
                "folio_ini": one,
                "folio_fin": one,
                "papel_ini": one,
                "papel_fin": one,
                "num_minuta": one,
                "num_escritura": one,
                "fecha_escritura": correlatives.today_iso(),
                "status": models.NotarizationReservation.Status.PENDING,
                "held_by": user,
            }

        folio = correlatives.bump_folio_papel_string(
            last.folio_fin or last.folio_ini or ""
        )
        papel = correlatives.bump_folio_papel_string(
            last.papel_fin or last.papel_ini or ""
        )
        return {
            "idtipkar": idtipkar,
            "kardex": kardex,
            "fecha_conclusion": last.fecha_conclusion,
            "folio_ini": folio,
            "folio_fin": folio,
            "papel_ini": papel,
            "papel_fin": papel,
            "num_minuta": correlatives.bump_int_string(last.num_minuta),
            "num_escritura": correlatives.bump_int_string(last.num_escritura),
            "fecha_escritura": correlatives.today_iso(),
            "status": models.NotarizationReservation.Status.PENDING,
            "held_by": user,
        }

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        if not user.is_authenticated:
            raise PermissionDenied("Authentication required to reserve.")

        idtipkar = serializer.validated_data["idtipkar"]

        self._release_stale_pending_on_create(idtipkar)
        active = self._active_pending_reservation(idtipkar)
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

        kardex = serializer.validated_data["kardex"].strip()
        if not kardex:
            raise ValidationError({"kardex": "This field may not be blank."})

        year = correlatives.correlative_year_today()
        payload = self._build_reservation_fields(
            kardex=kardex, idtipkar=idtipkar, year=year, user=user
        )
        serializer.save(**payload)
