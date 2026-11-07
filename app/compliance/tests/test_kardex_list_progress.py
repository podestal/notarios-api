from types import SimpleNamespace

from django.test import SimpleTestCase

from compliance.services.kardex_list_progress import (
    KardexBundle,
    list_tone,
    score_bundle,
)


def _cliente(**overrides):
    base = dict(
        idcontratante="C1",
        tipper="N",
        prinom="Juan",
        apepat="Perez",
        apemat="Lopez",
        segnom="",
        nombre="Juan Perez",
        razonsocial="",
        numdoc="12345678",
        idtipdoc=1,
        idubigeo="150101",
        telfijo="014445555",
        telcel="",
        email="juan@example.com",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _bundle(**overrides):
    row = overrides.pop(
        "row",
        SimpleNamespace(
            kardex="A1",
            idtipkar=1,
            codactos="016",
            numescritura="12",
            fechaescritura="2026-01-01",
            fechaconclusion="01/01/2026",
            folioini="",
            foliofin="",
            papelini="",
            papelfin="",
            numminuta="",
            fechaminuta="",
            numinstrmento="",
            txa_minuta="",
            papeltrasladoini="",
            papeltrasladofin="",
        ),
    )
    cliente = overrides.pop("cliente", _cliente())
    base = dict(
        row=row,
        contratantes=[SimpleNamespace(idcontratante="C1", kardex="A1")],
        clientes={"C1": cliente} if cliente else {},
        actos=[
            SimpleNamespace(
                idcontratante="C1",
                idcondicion="1",
                ofondo="",
                uif="",
                parte="",
                formulario="",
                monto="",
            )
        ],
        patrimoniales=[],
        medios=[],
        bienes=[],
        rentas=[],
        tipos={
            "016": SimpleNamespace(
                idtipoacto="016",
                cuantia="N",
                mediospago="N",
                origenfondo="N",
                novalidapatri="S",
            )
        },
        valid_ubigeo={"150101"},
        has_document=False,
    )
    base.update(overrides)
    return KardexBundle(**base)


class ListToneTests(SimpleTestCase):
    def test_errors_cannot_reach_complete(self):
        self.assertEqual(list_tone(["done"] * 6, 1, 0), "incomplete")

    def test_warnings_stay_a_warning_when_stages_are_finished(self):
        self.assertEqual(list_tone(["done"] * 5 + ["warning"], 0, 2), "warning")

    def test_clean_is_complete(self):
        self.assertEqual(list_tone(["done"] * 6, 0, 0), "complete")

    def test_an_idle_stage_is_incomplete(self):
        self.assertEqual(list_tone(["done"] * 5 + ["idle"], 0, 1), "incomplete")


class ScoreBundleTests(SimpleTestCase):
    def test_finished_kardex_is_complete(self):
        self.assertEqual(score_bundle(_bundle()), "complete")

    def test_missing_contact_does_not_block_list_complete(self):
        """List matches the modal: contact avisos are not invented here."""
        bundle = _bundle(cliente=_cliente(telfijo="", telcel="", email=""))
        self.assertEqual(score_bundle(bundle), "complete")

    def test_a_name_gap_is_incomplete(self):
        bundle = _bundle(cliente=_cliente(apepat=""))
        self.assertEqual(score_bundle(bundle), "incomplete")

    def test_nothing_saved_is_incomplete(self):
        row = SimpleNamespace(
            kardex="A9",
            idtipkar=1,
            codactos="",
            numescritura="",
            fechaescritura="",
            fechaconclusion="",
            folioini="",
            foliofin="",
            papelini="",
            papelfin="",
            numminuta="",
            fechaminuta="",
            numinstrmento="",
            txa_minuta="",
            papeltrasladoini="",
            papeltrasladofin="",
        )
        bundle = _bundle(row=row, contratantes=[], clientes={}, actos=[], tipos={})
        self.assertEqual(score_bundle(bundle), "incomplete")

    def test_types_without_patrimonial_can_still_complete(self):
        row = _bundle().row
        row.idtipkar = 2
        bundle = _bundle(row=row, tipos={}, patrimoniales=[])
        self.assertEqual(score_bundle(bundle), "complete")
