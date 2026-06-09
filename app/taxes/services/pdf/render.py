import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm as mm_unit
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PAGE_WIDTH = 80 * mm_unit
PAGE_HEIGHT = 280 * mm_unit
MARGIN = 4 * mm_unit


def _styles():
    base = getSampleStyleSheet()
    return {
        "center": ParagraphStyle(
            "center",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
        ),
        "center_bold": ParagraphStyle(
            "center_bold",
            parent=base["Normal"],
            fontName="Courier-Bold",
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
        ),
        "left": ParagraphStyle(
            "left",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=8,
            leading=10,
            alignment=TA_LEFT,
        ),
        "left_bold": ParagraphStyle(
            "left_bold",
            parent=base["Normal"],
            fontName="Courier-Bold",
            fontSize=8,
            leading=10,
            alignment=TA_LEFT,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=7,
            leading=9,
            alignment=TA_CENTER,
        ),
        "anulado": ParagraphStyle(
            "anulado",
            parent=base["Normal"],
            fontName="Courier-Bold",
            fontSize=10,
            leading=12,
            alignment=TA_CENTER,
            textColor=colors.red,
        ),
    }


def render_ingreso_pdf(context: dict) -> bytes:
    styles = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )

    story = []
    add = story.append
    p = lambda text, style="center": Paragraph(text, styles[style])

    add(p(context["denominacion_emisor"], "center_bold"))
    add(p(context["direccion_emisor"]))
    add(p(context["ubigeo_emisor"]))
    add(p(f"RUC: {context['ruc_emisor']}"))
    add(p(f"{context['telefono']}/{context['email']}"))
    add(
        Table(
            [
                [
                    Paragraph(f"{context['comprobante']} :", styles["center_bold"]),
                    Paragraph(
                        f"{context['serie']} - {context['numero']}",
                        styles["center_bold"],
                    ),
                ]
            ],
            colWidths=[PAGE_WIDTH * 0.55, PAGE_WIDTH * 0.45],
        )
    )
    add(Spacer(1, 4))

    if context["comprobante_anulado"]:
        add(p("ANULADO", "anulado"))
        add(Spacer(1, 4))

    add(p("ADQUIRIENTE", "left_bold"))
    add(
        p(
            f"<b>{context['abr_tipo_documento']}</b>: {context['ruc_cliente']}",
            "left",
        )
    )
    add(p(context["denominacion_cliente"], "left"))
    add(p(context["direccion_cliente"], "left"))
    add(p(f"<b>FECHA EMISIÓN: </b>{context['fecha_emision']}", "left"))
    add(p(f"<b>HORA: </b>{context['hora_emision']}", "left"))
    add(Spacer(1, 6))

    rows = [
        [
            Paragraph("CANT.", styles["left_bold"]),
            Paragraph("DESCRIPCIÓN", styles["left_bold"]),
            Paragraph("P/U", styles["center_bold"]),
            Paragraph("TOTAL", styles["center_bold"]),
        ]
    ]
    for linea in context["lineas"]:
        descripcion = linea["descripcion"]
        if linea["detalle"] and linea["detalle"] != "-":
            descripcion = f"{descripcion}<br/><font size='6'>{linea['detalle']}</font>"
        rows.append(
            [
                Paragraph(str(linea["cantidad"]), styles["center"]),
                Paragraph(descripcion, styles["left"]),
                Paragraph(str(linea["precio_unitario"]), styles["center"]),
                Paragraph(str(linea["total"]), styles["center"]),
            ]
        )

    table = Table(
        rows,
        colWidths=[
            PAGE_WIDTH * 0.12,
            PAGE_WIDTH * 0.48,
            PAGE_WIDTH * 0.18,
            PAGE_WIDTH * 0.18,
        ],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
                ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    add(table)

    total_table = Table(
        [
            [
                Paragraph("TOTAL", styles["center_bold"]),
                Paragraph("S/", styles["center_bold"]),
                Paragraph(str(context["total"]), styles["center_bold"]),
            ]
        ],
        colWidths=[PAGE_WIDTH * 0.6, PAGE_WIDTH * 0.12, PAGE_WIDTH * 0.22],
    )
    total_table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
            ]
        )
    )
    add(total_table)
    add(Spacer(1, 6))
    add(p(f"IMPORTE EN LETRAS: {context['total_letras']}"))

    if context["observaciones"]:
        add(p(f"OBS.: {context['observaciones']}"))

    add(p(f"Atendido por: {context['usuario']}", "small"))
    add(
        p(
            "Representación impresa de la <br/>"
            f"{context['comprobante']} , <br/>"
            "<font size='6'>Sólo para control interno, sirvase canjear por su comprobante de pago "
            "boleta de venta o factura el día de realizado el servicio.</font>",
        )
    )

    qr_image = Image(
        io.BytesIO(context["qr_image_bytes"]),
        width=28 * mm_unit,
        height=28 * mm_unit,
    )
    qr_image.hAlign = "CENTER"
    add(qr_image)
    add(p("GRACIAS POR SU PREFERENCIA"))

    doc.build(story)
    return buffer.getvalue()
