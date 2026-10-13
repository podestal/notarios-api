from unittest import mock

from django.test import SimpleTestCase

from sisgen.services.sisgen_error_explainer import (
    KardexContext,
    explain_document_errors,
    explain_soap_message,
    fix_mojibake,
    locate_xml_position,
    split_code,
)

REQUEST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<documentosNotariales>
\t<DocumentoNotarial>
\t\t<Documento>
\t\t\t<NumKardex>K119-2026</NumKardex>
\t\t</Documento>
\t\t<Maestros>
\t\t\t<PersonasJuridicas>
\t\t\t\t<PersonaJuridica id="0000009253">
\t\t\t\t<DocsIdentificativos>
\t\t\t\t\t<DocIdentificativo>
\t\t\t\t\t\t<TipoDocIdentidad>01</TipoDocIdentidad>
\t\t\t\t\t</DocIdentificativo>
\t\t\t\t</DocsIdentificativos>
\t\t\t\t<RazonSocial>AMI &amp;amp; RAI E.I.R.L.</RazonSocial>
\t\t\t\t</PersonaJuridica>
\t\t\t</PersonasJuridicas>
\t\t</Maestros>
\t</DocumentoNotarial>
</documentosNotariales>
"""


class FakeContext(KardexContext):
    def __init__(self, personas=None, patrimoniales=None, medios=None):
        super().__init__("K1-2026")
        self._cache = {
            "personas": personas or [],
            "patrimonial": patrimoniales or [],
            "medios": medios or [],
        }

    def acto_nombre(self, cod_ancert):
        return {"0109": "DONACION"}.get(cod_ancert, "")


class SisgenErrorExplainerTests(SimpleTestCase):
    def test_fix_mojibake(self):
        self.assertEqual(
            fix_mojibake("RO12: FORMA DE PAGO NO ADMITIDO PARA LA OPERACIÃ³N"),
            "RO12: FORMA DE PAGO NO ADMITIDO PARA LA OPERACIÓN",
        )
        self.assertEqual(fix_mojibake("OPERACIÓN"), "OPERACIÓN")

    def test_split_code_variants(self):
        self.assertEqual(split_code("EC40: TEXTO")[0], "EC40")
        self.assertEqual(split_code("EC40 - TEXTO")[0], "EC40")
        self.assertEqual(split_code("EC40 TEXTO"), ("EC40", "TEXTO"))
        self.assertEqual(split_code("Transaction rolled back")[0], "")

    def test_duplicates_and_generic_variants_collapse(self):
        ctx = FakeContext(personas=[{"idcliente": "9074", "tipper": "N", "prinom": "ANA", "apepat": "RUIZ"}])
        out = explain_document_errors(
            [
                "EC48: EL REPRESENTANTE CON IDMAESTRO 9074 ESTÁ REPETIDO.",
                "EC48 - NO PERMITIR REPRESENTANTES REPETIDOS",
                "EC36: EL ACTO JURÃ­DICO 0109 REQUIERE MEDIOS DE PAGO",
                "EC36 - EL ACTO JURÃ­DICO 0109 REQUIERE MEDIOS DE PAGO",
            ],
            kardex="K1-2026",
            ctx=ctx,
        )
        self.assertEqual([e["codigo"] for e in out], ["EC48", "EC36"])
        self.assertIn("ANA RUIZ", out[0]["mensaje_usuario"])
        self.assertIn("DONACION", out[1]["mensaje_usuario"])
        self.assertEqual(out[1]["campos"][0]["seccion"], "UIF/PDT Patrimonial")

    def test_ro04_lists_persons_without_profession(self):
        ctx = FakeContext(
            personas=[
                {"idcliente": "1", "tipper": "N", "prinom": "LUIS", "apepat": "PEREZ", "idprofesion": None, "detaprofesion": ""},
                {"idcliente": "2", "tipper": "N", "prinom": "EVA", "apepat": "DIAZ", "idprofesion": 5},
                {"idcliente": "3", "tipper": "J", "razonsocial": "EMPRESA SAC"},
            ]
        )
        out = explain_document_errors(
            ["RO04: EL CAMPO PROFESION ES OBLIGATORIO PARA PERSONAS NATURALES"], kardex="K1-2026", ctx=ctx
        )
        self.assertEqual([c["referencia"] for c in out[0]["campos"]], ["LUIS PEREZ"])

    def test_vl15_shows_amounts(self):
        ctx = FakeContext(
            patrimoniales=[{"itemmp": "1", "desacto": "COMPRAVENTA", "importetrans": 7000}],
            medios=[{"itemmp": "1", "importemp": 5000}],
        )
        out = explain_document_errors(
            ["VL15: LA SUMA DE LAS CUANTÃ­AS DE LOS MEDIOS DE PAGO DEBE COINCIDIR CON LA CUANTÃ­A DE LA OPERACIÃ³N"],
            kardex="K1-2026",
            ctx=ctx,
        )
        self.assertEqual(out[0]["campos"][0]["valor_actual"], "cuantía 7,000.00 · medios 5,000.00")

    def test_unknown_code_keeps_readable_text(self):
        out = explain_document_errors(["ZZ99: ALGO NUEVO"], kardex="K1-2026", ctx=FakeContext())
        self.assertEqual(out[0]["titulo"], "Observación de SISGEN (ZZ99)")
        self.assertEqual(out[0]["mensaje_usuario"], "Algo nuevo")

    def test_locate_xml_position_finds_field_person_and_kardex(self):
        loc = locate_xml_position(REQUEST_XML, 12, 46)
        self.assertEqual(loc["elemento"], "TipoDocIdentidad")
        self.assertEqual(loc["valor"], "01")
        self.assertEqual(loc["kardex"], "K119-2026")
        self.assertEqual(loc["persona_tipo"], "J")
        self.assertEqual(loc["persona"], "AMI & RAI E.I.R.L.")

    def test_soap_message_field_from_type_name_without_location(self):
        out = explain_soap_message(
            "cvc-maxLength-valid: Value 'A LA FIRMA DEL INSTRUMENTO PUBLICO NOTARIAL PROTOCOLAR' with length = '54' "
            "is not facet-valid with respect to maxLength '40' for type '#AnonType_DescripcionMomentoPagoMediosPagoType'. "
            "En la Fila: 241 Columna: 107"
        )
        self.assertEqual(out["titulo"], "Texto demasiado largo en Oportunidad de pago (descripción)")
        self.assertEqual(out["campos"][0]["seccion"], "UIF/PDT Patrimonial")

    def test_soap_message_unknown_field_suggests_resend(self):
        out = explain_soap_message("null En la Fila: 123 Columna: 51")
        self.assertEqual(out["titulo"], "Falta un dato")
        self.assertIn("vuelva a enviar", out["que_hacer"])
        self.assertEqual(out["campos"], [])

    def test_ro04_offers_profession_quick_fix(self):
        ctx = FakeContext(
            personas=[{"idcontratante": 77, "idcliente": "1", "tipper": "N", "prinom": "LUIS", "idprofesion": None}]
        )
        out = explain_document_errors(["RO04: PROFESION OBLIGATORIA"], kardex="K1-2026", ctx=ctx)
        self.assertEqual(
            out[0]["campos"][0]["accion"],
            {"tipo": "cliente2_profesion", "idcontratante": "77", "idprofesion": None},
        )

    def test_vl34_no_requiere_suggests_vacio(self):
        ctx = FakeContext(patrimoniales=[{"itemmp": "000206", "desacto": "ADJUDICACION", "idoppago": 6}])
        out = explain_document_errors(
            ["VL34: LA OPORTUNIDAD DE PAGO DEBE SER NO REQUIERE"], kardex="K1-2026", ctx=ctx
        )
        accion = out[0]["campos"][0]["accion"]
        self.assertEqual(accion["tipo"], "patrimonial_oportunidad_pago")
        self.assertEqual((accion["itemmp"], accion["idoppago"], accion["sugerido"]), ("000206", "6", "10"))

    def test_campos_without_quick_fix_link_to_kardex_tab(self):
        out = explain_document_errors(
            ["EC36: EL ACTO JURÃ­DICO 0109 REQUIERE MEDIOS DE PAGO"], kardex="K1-2026", ctx=FakeContext()
        )
        self.assertEqual(out[0]["campos"][0]["accion"], {"tipo": "ir_kardex", "seccion": "patrimonial"})

    def test_soap_tipo_documento_resolves_contratante(self):
        ctx = FakeContext(
            personas=[{"idcontratante": 501, "idcliente": "0000009253", "tipper": "J", "idtipdoc": 1, "numdoc": "123"}]
        )
        loc = locate_xml_position(REQUEST_XML, 12, 46)
        out = explain_soap_message(
            "cvc-enumeration-valid: Value '01' is not facet-valid with respect to enumeration "
            "'[08, 09, 10, 12, 13]'. En la Fila: 12 Columna: 46",
            location=loc,
            ctx=ctx,
        )
        self.assertEqual(
            out["campos"][0]["accion"],
            {"tipo": "cliente2_tipo_documento", "idcontratante": "501", "tipper": "J", "idtipdoc": 1, "numdoc": "123"},
        )

    def test_soap_forma_pago_matches_patrimonial_by_acto(self):
        ctx = FakeContext(
            patrimoniales=[
                {"itemmp": "1", "cod_ancert": "0109", "fpago": "1"},
                {"itemmp": "2", "cod_ancert": "0201", "fpago": "2"},
            ]
        )
        out = explain_soap_message(
            "cvc-enumeration-valid: Value '9' is not facet-valid with respect to enumeration '[1, 2, 3]' "
            "for type '#AnonType_FormaPagoOperacionType'.",
            location={"elemento": "FormaPago", "acto_codigo": "0201", "kardex": "K1-2026"},
            ctx=ctx,
        )
        self.assertEqual(out["campos"][0]["accion"], {"tipo": "patrimonial_forma_pago", "itemmp": "2", "fpago": "2"})

    def test_lookup_failure_does_not_break_explanation(self):
        ctx = KardexContext("K1-2026")
        broken = mock.Mock()
        broken.cursor.side_effect = RuntimeError("db down")
        with mock.patch("django.db.connection", broken):
            out = explain_document_errors(
                ["RO12: FORMA DE PAGO NO ADMITIDO PARA LA OPERACIÃ³N"], kardex="K1-2026", ctx=ctx
            )
        self.assertEqual(out[0]["titulo"], "Forma de pago no admitida para el acto")
        self.assertEqual(out[0]["campos"][0]["campo"], "Forma de pago")
