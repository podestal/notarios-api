from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, override_settings

from documentos.models import DocumentoBien
from documentos.services.apply_vehicular import (
    apply_documento_vehicular_to_detalle,
    list_pending_vehiculares,
    parsed_to_detalle_fields,
    unlink_documentos_for_detveh,
    unlink_documentos_for_kardex_acto,
)


class ParsedToDetalleFieldsTests(SimpleTestCase):
    def test_maps_core_vehicle_fields(self):
        doc = DocumentoBien(
            placa="V5W564",
            partida="60032609",
            parsed={
                "vehiculo": {
                    "placa": "V5W564",
                    "marca": "DAEWOO",
                    "modelo": "TICO",
                    "numero_motor": "F8C312031",
                    "numero_serie": "KLY3S11BDSC260706",
                    "carroceria": "SEDAN",
                    "anio_fabricacion": "1995",
                    "combustible": "GASOLINA",
                    "color_1": "AMARILLO DORADO",
                    "partida": "60032609",
                    "numero_ruedas": "4",
                    "numero_cilindros": "3",
                    "categoria": "M1",
                }
            },
        )
        fields = parsed_to_detalle_fields(doc, kardex="A346-2026", idtipacto="094")
        self.assertEqual(fields["numplaca"], "V5W564")
        self.assertEqual(fields["marca"], "DAEWOO")
        self.assertEqual(fields["motor"], "F8C312031")
        self.assertEqual(fields["kardex"], "A346-2026")
        self.assertEqual(fields["idtipacto"], "094")
        self.assertEqual(fields["idplaca"], "P")


class ApplyDocumentoVehicularTests(SimpleTestCase):
    def test_apply_creates_detalle_and_links_documento(self):
        doc = MagicMock()
        doc.status = DocumentoBien.STATUS_PARSED
        doc.placa = "V5W564"
        doc.partida = "60032609"
        doc.parsed = {
            "vehiculo": {
                "placa": "V5W564",
                "marca": "DAEWOO",
                "modelo": "TICO",
                "numero_motor": "ABC",
                "numero_serie": "SERIE12345678901234567890XX",
                "partida": "60032609",
            }
        }
        detalle = MagicMock(detveh=99)

        with patch(
            "documentos.services.apply_vehicular.transaction.atomic"
        ) as atomic, patch(
            "documentos.services.apply_vehicular.DocumentoBien.objects"
        ) as objects, patch("notaria.models") as models_mod:
            atomic.return_value.__enter__.return_value = None
            atomic.return_value.__exit__.return_value = False

            objects.select_for_update.return_value.filter.return_value.first.return_value = (
                doc
            )
            models_mod.Detallevehicular.objects.filter.return_value.order_by.return_value.first.return_value = (
                None
            )
            models_mod.Detallevehicular.objects.create.return_value = detalle
            models_mod.Kardex.objects.filter.return_value.exclude.return_value.update.return_value = (
                0
            )

            out_doc, out_det = apply_documento_vehicular_to_detalle(
                documento_id=10, kardex="A346-2026", idtipacto="094"
            )

        self.assertIs(out_doc, doc)
        self.assertIs(out_det, detalle)
        self.assertEqual(doc.detveh, 99)
        self.assertEqual(doc.status, DocumentoBien.STATUS_APPLIED)
        self.assertEqual(doc.kardex, "A346-2026")
        self.assertEqual(doc.idtipacto, "094")
        doc.save.assert_called()
        create_kwargs = models_mod.Detallevehicular.objects.create.call_args.kwargs
        self.assertEqual(create_kwargs["numplaca"], "V5W564")
        self.assertEqual(create_kwargs["numserie"], "SERIE12345678901234567890XX"[:30])


@override_settings(DOCUMENTOS_NOTARIA_ROOT="/tmp/documentos_notaria_test")
class PendingListTests(TestCase):
    def test_pending_only_parsed_unlinked(self):
        parsed = DocumentoBien.objects.create(
            tipo=DocumentoBien.TIPO_VEHICULAR,
            original_filename="a.pdf",
            stored_filename="a.pdf",
            relative_path="vehiculares/a.pdf",
            status=DocumentoBien.STATUS_PARSED,
            placa="AAA111",
        )
        DocumentoBien.objects.create(
            tipo=DocumentoBien.TIPO_VEHICULAR,
            original_filename="b.pdf",
            stored_filename="b.pdf",
            relative_path="vehiculares/b.pdf",
            status=DocumentoBien.STATUS_APPLIED,
            placa="BBB222",
            detveh=1,
        )
        ids = list(list_pending_vehiculares().values_list("id", flat=True))
        self.assertEqual(ids, [parsed.id])

    def test_delete_removes_row_and_file(self):
        from pathlib import Path

        from documentos.services.upload import delete_documento_bien

        root = Path("/tmp/documentos_notaria_test")
        rel = "vehiculares/del_me.pdf"
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4 delete-me")
        doc = DocumentoBien.objects.create(
            tipo=DocumentoBien.TIPO_VEHICULAR,
            original_filename="del_me.pdf",
            stored_filename="del_me.pdf",
            relative_path=rel,
            status=DocumentoBien.STATUS_PARSED,
            placa="DEL001",
        )
        doc_id = doc.id
        delete_documento_bien(doc)
        self.assertFalse(DocumentoBien.objects.filter(pk=doc_id).exists())
        self.assertFalse(path.exists())

    def test_unlink_for_detveh_restores_pending(self):
        doc = DocumentoBien.objects.create(
            tipo=DocumentoBien.TIPO_VEHICULAR,
            original_filename="linked.pdf",
            stored_filename="linked.pdf",
            relative_path="vehiculares/linked.pdf",
            status=DocumentoBien.STATUS_APPLIED,
            placa="LNK001",
            detveh=42,
            kardex="A100-2026",
            idtipacto="094",
        )
        changed = unlink_documentos_for_detveh(42)
        doc.refresh_from_db()
        self.assertEqual(changed, 1)
        self.assertIsNone(doc.detveh)
        self.assertEqual(doc.kardex, "")
        self.assertEqual(doc.idtipacto, "")
        self.assertEqual(doc.status, DocumentoBien.STATUS_PARSED)
        self.assertEqual(
            list(list_pending_vehiculares().values_list("id", flat=True)),
            [doc.id],
        )

    def test_unlink_for_kardex_acto(self):
        DocumentoBien.objects.create(
            tipo=DocumentoBien.TIPO_VEHICULAR,
            original_filename="k.pdf",
            stored_filename="k.pdf",
            relative_path="vehiculares/k.pdf",
            status=DocumentoBien.STATUS_APPLIED,
            placa="K001",
            detveh=7,
            kardex="A200-2026",
            idtipacto="094",
        )
        changed = unlink_documentos_for_kardex_acto(
            kardex="A200-2026", idtipacto="094"
        )
        self.assertEqual(changed, 1)
        self.assertEqual(list_pending_vehiculares().count(), 1)
