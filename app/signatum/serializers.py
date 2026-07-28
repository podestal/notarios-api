from rest_framework import serializers

from . import models


class NotarizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Notarization
        fields = "__all__"


class NotarizationReservationSerializer(serializers.ModelSerializer):
    """Full reservation; use for retrieve, list, update."""

    held_by_username = serializers.SerializerMethodField()

    class Meta:
        model = models.NotarizationReservation
        fields = "__all__"
        read_only_fields = (
            "idtipkar",
            "status",
            "held_by",
            "created_at",
        )

    def get_held_by_username(self, obj):
        user = getattr(obj, "held_by", None)
        return getattr(user, "username", None) if user is not None else None


class CreateNotarizationReservationSerializer(serializers.ModelSerializer):
    """POST: `kardex` + `idtipkar` (tipo); correlatives are filled server-side per tipo/year."""

    class Meta:
        model = models.NotarizationReservation
        fields = ("kardex", "idtipkar")


class SerieNotarialSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.SerieNotarial
        fields = "__all__"


class CorrelativeCounterSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CorrelativeCounter
        fields = "__all__"
        read_only_fields = ("id", "updated_at")


class AdminReleaseReservationSerializer(serializers.Serializer):
    """Force-release a pending reservation (stuck lock)."""

    status = serializers.ChoiceField(
        choices=("EX", "CA"),
        default="EX",
        help_text="EX=expired, CA=cancelled",
    )
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class AdminReverseReservationSerializer(serializers.Serializer):
    """Undo a committed reservation as if it was never used."""

    reason = serializers.CharField(required=False, allow_blank=True, default="")
    clear_kardex = serializers.BooleanField(
        required=False,
        default=True,
        help_text=(
            "Clear kardex escrituración fields when they still match this commit."
        ),
    )
    hard_delete = serializers.BooleanField(
        required=False,
        default=False,
        help_text="If true, delete the reservation row; otherwise mark status=RV.",
    )


class AdminSetCounterSerializer(serializers.Serializer):
    """Create or update the correlative counter for year + idtipkar."""

    year = serializers.IntegerField(min_value=2000, max_value=2100)
    idtipkar = serializers.IntegerField(min_value=1)
    next_num_escritura = serializers.IntegerField(min_value=1, required=False)
    next_num_minuta = serializers.IntegerField(min_value=1, required=False)
    last_folio = serializers.CharField(
        required=False, allow_blank=True, max_length=30
    )
    freed_num_escrituras = serializers.JSONField(required=False)


class AdminPatchCounterSerializer(serializers.Serializer):
    next_num_escritura = serializers.IntegerField(min_value=1, required=False)
    next_num_minuta = serializers.IntegerField(min_value=1, required=False)
    last_folio = serializers.CharField(
        required=False, allow_blank=True, max_length=30
    )
    freed_num_escrituras = serializers.JSONField(required=False)


class AdminPatchNotarizationSerializer(serializers.Serializer):
    """Correct committed correlatives; optionally mirror onto legacy kardex."""

    num_escritura = serializers.CharField(required=False, allow_blank=True, max_length=100)
    num_minuta = serializers.CharField(required=False, allow_blank=True, max_length=100)
    folio_ini = serializers.CharField(required=False, allow_blank=True, max_length=30)
    folio_fin = serializers.CharField(required=False, allow_blank=True, max_length=30)
    papel_ini = serializers.CharField(required=False, allow_blank=True, max_length=30)
    papel_fin = serializers.CharField(required=False, allow_blank=True, max_length=30)
    fecha_escritura = serializers.CharField(required=False, allow_blank=True, max_length=10)
    fecha_conclusion = serializers.CharField(required=False, allow_blank=True, max_length=10)
    sync_kardex = serializers.BooleanField(
        required=False,
        default=True,
        help_text="Also update matching kardex row correlative fields.",
    )
    sync_counter_folio = serializers.BooleanField(
        required=False,
        default=False,
        help_text="If true, set counter.last_folio from this notarization folio_fin.",
    )
