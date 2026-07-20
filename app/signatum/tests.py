from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from signatum import allocation, models
from signatum.services import finalize_notarization_from_reservation

User = get_user_model()


class AllocateCorrelativesTests(TestCase):
    def test_allocate_starts_at_one_and_advances(self):
        with transaction.atomic():
            first = allocation.allocate_correlatives(year=2026, idtipkar=3)
            second = allocation.allocate_correlatives(year=2026, idtipkar=3)

        self.assertEqual(first.num_escritura, "1")
        self.assertEqual(first.folio, "1")
        self.assertEqual(second.num_escritura, "2")
        # folio not advanced until commit
        self.assertEqual(second.folio, "1")

        counter = models.CorrelativeCounter.objects.get(year=2026, idtipkar=3)
        self.assertEqual(counter.next_num_escritura, 3)
        self.assertEqual(counter.last_folio, "")

    def test_advance_folio_on_commit_then_next_reserve_bumps(self):
        with transaction.atomic():
            first = allocation.allocate_correlatives(year=2026, idtipkar=3)
            allocation.advance_folio_on_commit(
                year=2026, idtipkar=3, folio_fin="10 VTA"
            )
            second = allocation.allocate_correlatives(year=2026, idtipkar=3)

        self.assertEqual(first.folio, "1")
        self.assertEqual(second.folio, "11")
        self.assertEqual(second.num_escritura, "2")

    def test_seed_from_existing_notarization(self):
        models.Notarization.objects.create(
            idtipkar=3,
            kardex="A100-2026",
            folio_ini="200",
            folio_fin="200 VTA",
            num_escritura="138",
            num_minuta="50",
            fecha_escritura="2026-07-17",
        )
        with transaction.atomic():
            allocated = allocation.allocate_correlatives(year=2026, idtipkar=3)

        self.assertEqual(allocated.num_escritura, "139")
        self.assertEqual(allocated.folio, "201")


class FinalizeReservationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="notario28", password="x")
        self.other = User.objects.create_user(username="other", password="x")

    def _reservation(self, **overrides):
        defaults = {
            "idtipkar": 3,
            "kardex": "A143-2026",
            "folio_ini": "201",
            "folio_fin": "201",
            "num_escritura": "139",
            "num_minuta": "",
            "fecha_escritura": "2026-07-17",
            "status": models.NotarizationReservation.Status.PENDING,
            "held_by": self.user,
        }
        defaults.update(overrides)
        return models.NotarizationReservation.objects.create(**defaults)

    def _kardex(self, **overrides):
        class K:
            pass

        k = K()
        k.kardex = "A143-2026"
        k.idtipkar = 3
        k.numescritura = "138"
        k.folioini = "201"
        k.foliofin = "202"
        k.papelini = "5935401"
        k.papelfin = "5935402"
        k.numminuta = ""
        k.fechaescritura = "2026-07-17"
        k.fechaconclusion = ""
        saved = {"fields": None}

        def save(*, update_fields=None):
            saved["fields"] = update_fields

        k.save = save
        for key, value in overrides.items():
            setattr(k, key, value)
        k._saved = saved
        return k

    def test_finalize_overwrites_stale_numescritura(self):
        reservation = self._reservation()
        kardex = self._kardex()

        with patch("signatum.services.allocation.advance_folio_on_commit"):
            notarization = finalize_notarization_from_reservation(
                kardex_instance=kardex,
                reservation_id=reservation.id,
                user=self.user,
            )

        self.assertEqual(kardex.numescritura, "139")
        self.assertIn("numescritura", kardex._saved["fields"] or [])
        self.assertEqual(notarization.num_escritura, "139")
        reservation.refresh_from_db()
        self.assertEqual(
            reservation.status, models.NotarizationReservation.Status.COMMITTED
        )

    def test_finalize_rejects_other_users_reservation(self):
        reservation = self._reservation()
        kardex = self._kardex()

        with self.assertRaises(ValidationError):
            finalize_notarization_from_reservation(
                kardex_instance=kardex,
                reservation_id=reservation.id,
                user=self.other,
            )
