import os
import io
import traceback
from typing import Dict, Any, Optional
from datetime import datetime

from django.db import connection
from django.http import HttpResponse, JsonResponse
from rest_framework.response import Response
from rest_framework import status

from docxtpl import DocxTemplate
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.shared import OxmlElement, qn

import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from ..shared.base_r2_documents import get_s3_client, BaseR2DocumentService
from ..utils import NumberToLetterConverter


class CartasNotarialesDocumentService(BaseR2DocumentService):
    """
    Service for generating and retrieving Certificación de Entrega de Carta Notarial documents.

    - Template expected in R2: 'CERTIFICACION ENTREGA DE CARTA NOTARIAL.docx'
    - Output filename: '__CARTA__{num_carta}.docx'
    - Stores under: rodriguez-zea/documentos/
    """

    def __init__(self) -> None:
        self.letras = NumberToLetterConverter()
        self.template_filename = "CERTIFICACION ENTREGA DE CARTA NOTARIAL.docx"

    def retrieve_carta_document(self, num_carta: str, mode: str = "download") -> HttpResponse:
        try:
            if not num_carta:
                return self.json_error(400, "num_carta is required to retrieve document")

            formatted_num_carta = self._format_num_carta(num_carta)
            filename = f"__CARTA__{formatted_num_carta}.docx"

            if mode == "open":
                return self._create_response(None, filename, num_carta, mode)

            s3 = get_s3_client()
            object_key = self._object_key_for_document(filename)
            response = s3.get_object(Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'), Key=object_key)
            buffer = io.BytesIO(response['Body'].read())
            return self._create_response(buffer, filename, num_carta, mode)
        except Exception as e:
            # Map not-found to 404 JSON
            if hasattr(e, 'response') and isinstance(getattr(e, 'response'), dict):
                code = e.response.get('Error', {}).get('Code')
                if code == 'NoSuchKey':
                    return self.json_error(404, "Document not found in R2. Generate it first.", {
                        'num_carta': num_carta,
                        'filename': f"__CARTA__{num_carta}.docx",
                    })
            traceback.print_exc()
            return self.json_error(500, f"Error retrieving document: {e}")

    def generate_carta_document(self, num_carta: str, mode: str = "download") -> HttpResponse:
        try:
            if not num_carta:
                return self.json_error(400, "num_carta is required to generate document")

            formatted_num_carta = self._format_num_carta(num_carta)
            filename = f"__CARTA__{formatted_num_carta}.docx"
            if self._document_exists_in_r2(filename):
                return self.json_error(409, "Document already exists. Use action=retrieve to fetch it.", {
                    'num_carta': formatted_num_carta,
                    'filename': filename,
                })

            template_bytes = self._get_template_from_r2()
            if template_bytes is None:
                return self.json_error(404, f"Template '{self.template_filename}' not found in 'rodriguez-zea/plantillas/'.")

            carta_data = self._get_carta_data(num_carta)
            if not carta_data:
                return self.json_error(404, f"ingreso_cartas record with num_carta {num_carta} not found")

            context: Dict[str, Any] = {}
            context.update(carta_data)
            context.update(self._get_notary_data())

            # Aliases to match template variable names (docxtpl is case-sensitive)
            context['contenido_carta'] = context.get('CONTENIDO_CARTA', '')
            context['fec_ingreso'] = context.get('FECHA_INGRESO_LETRAS', '')
            context['num_carta'] = context.get('NUM_CARTA_FMT', '')
            # Legacy placeholders from PHP template
            context['USUARIO'] = context.get('USUARIO', '') or ''
            context['USUARIO_DNI'] = context.get('USUARIO_DNI', '') or ''
            context['COMPROBANTE'] = context.get('COMPROBANTE', '') or 'sin'

            doc = DocxTemplate(io.BytesIO(template_bytes))
            doc.render(context)

            buffer = io.BytesIO()
            doc.save(buffer)
            self._save_document_to_r2(buffer, filename)
            return self._create_response(buffer, filename, num_carta, mode)
        except Exception as e:
            traceback.print_exc()
            return self.json_error(500, f"Error generating document: {e}")

    def _get_template_from_r2(self) -> Optional[bytes]:
        s3 = get_s3_client()
        object_key = self._object_key_for_template(self.template_filename)
        try:
            response = s3.get_object(Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'), Key=object_key)
            return response['Body'].read()
        except Exception:
            return None

    def _save_document_to_r2(self, buffer: io.BytesIO, filename: str) -> None:
        s3 = get_s3_client()
        object_key = self._object_key_for_document(filename)
        buffer.seek(0)
        s3.put_object(
            Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'),
            Key=object_key,
            Body=buffer.read(),
        )
        buffer.seek(0)

    def _create_response(self, buffer: Optional[io.BytesIO], filename: str, num_carta: str, mode: str = "download") -> HttpResponse:
        if mode == "open":
            s3 = get_s3_client()
            object_key = self._object_key_for_document(filename)
            try:
                url = s3.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': os.environ.get('CLOUDFLARE_R2_BUCKET'), 'Key': object_key},
                    ExpiresIn=3600,
                )
                response = JsonResponse({
                    'status': 'success', 'mode': 'open', 'url': url,
                    'filename': filename, 'num_carta': num_carta,
                    'message': 'Document is ready to be opened.'
                })
                response['Access-Control-Allow-Origin'] = '*'
                return response
            except Exception as e:
                return HttpResponse(f"Error generating pre-signed URL: {e}", status=500)
        if buffer is None:
            return HttpResponse("Error: Document buffer is missing for download mode.", status=500)
        buffer.seek(0)
        response = HttpResponse(buffer.read(), content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        response['Content-Length'] = str(buffer.getbuffer().nbytes)
        response['Access-Control-Allow-Origin'] = '*'
        return response

    def _get_notary_data(self) -> Dict[str, str]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT CONCAT(nombre, ' ', apellido) AS notario FROM confinotario")
            row = cursor.fetchone()
            if row:
                return {'NOTARIO': str(row[0]).upper() if row[0] else ''}
        return {'NOTARIO': ''}

    def _get_user_data(self, usuario_imprime: Optional[str]) -> Dict[str, str]:
        if not usuario_imprime:
            return {'USUARIO': '?', 'USUARIO_DNI': '?'}
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT loginusuario, dni FROM usuarios
                WHERE CONCAT(apepat,' ',prinom) = %s
                """,
                [usuario_imprime],
            )
            row = cursor.fetchone()
            if row:
                return {'USUARIO': row[0] or '?', 'USUARIO_DNI': row[1] or '?'}
            return {'USUARIO': '?', 'USUARIO_DNI': '?'}

    def _format_num_carta(self, raw: Optional[str]) -> str:
        if not raw or len(raw) < 6:
            return raw or ''
        # Format as NNNNNN-YYYY like PHP CONCAT(RIGHT(6), '-', LEFT(4))
        return f"{raw[-6:]}-{raw[:4]}"

    def _get_carta_data(self, num_carta: str) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 
                    num_carta,
                    conte_carta,
                    STR_TO_DATE(fec_entrega, '%%d/%%m/%%Y') AS fecha_diligencia,
                    hora_entrega,
                    STR_TO_DATE(fec_ingreso, '%%d/%%m/%%Y') AS fecha_ingreso
                FROM ingreso_cartas
                WHERE num_carta = %s
                """,
                [num_carta],
            )
            row = cursor.fetchone()
            if not row:
                return {}
            raw_num_carta = row[0]
            contenido = row[1] or ''
            fecha_diligencia = row[2]
            hora_entrega = row[3] or ''
            fecha_ingreso = row[4]

            # Prepare replacements in contenido (00/00/0000 -> dd/mm/YYYY, 00:00 -> hora_entrega)
            fecha_diligencia_ddmmyyyy = fecha_diligencia.strftime('%d/%m/%Y') if fecha_diligencia else ''
            contenido_replaced = contenido.replace('00/00/0000', fecha_diligencia_ddmmyyyy).replace('00:00', hora_entrega)

            data.update({
                'NUM_CARTA': raw_num_carta or '',
                'NUM_CARTA_FMT': self._format_num_carta(raw_num_carta),
                'CONTENIDO_CARTA': contenido_replaced,
                'FECHA_DILIGENCIA': fecha_diligencia_ddmmyyyy,
                'FECHA_DILIGENCIA_LETRAS': self.letras.date_to_letters(fecha_diligencia).upper() if fecha_diligencia else '',
                'HORA_DILIGENCIA': hora_entrega,
                'FECHA_INGRESO_LETRAS': self.letras.date_to_letters(fecha_ingreso).lower() if fecha_ingreso else '',
            })
        return data 


class CartasNotarialesReportService:
    """Service for generating cartas notariales reports"""
    
    def _get_report_data(self, desde, hasta):
        """Fetch data for the report"""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    ic.num_carta AS num_carta,
                    DATE_FORMAT(STR_TO_DATE(ic.fec_ingreso,'%%d/%%m/%%Y'),'%%d/%%m/%%Y') AS fec_ingreso,
                    ic.fec_entrega AS fec_entrega,
                    ic.hora_entrega AS hora_entrega,
                    ic.nom_destinatario AS destinatario,
                    ic.nom_remitente AS remitente,
                    u.nomdis as zona,
                    ic.dir_destinatario,
                    ic.id_remitente as dni_remitente,
                    ic.dni_destinatario,
                    ic.recepcion,
                    ic.firmo
                FROM ingreso_cartas ic
                INNER JOIN ubigeo u ON u.coddis = ic.zona_destinatario
                WHERE STR_TO_DATE(ic.fec_ingreso,'%%d/%%m/%%Y') 
                      BETWEEN STR_TO_DATE(%s,'%%d/%%m/%%Y') AND STR_TO_DATE(%s,'%%d/%%m/%%Y')
                ORDER BY ic.num_carta ASC
            """, [desde, hasta])
            
            return cursor.fetchall()
    
    def _get_notary_info(self):
        """Get notary configuration info"""
        with connection.cursor() as cursor:
            cursor.execute("SELECT nombre, apellido FROM confinotario")
            result = cursor.fetchone()
            if result:
                return f"{result[0]} {result[1]}"
            return "NOTARIO"
    
    def _format_date_in_spanish(self, date_str):
        """Convert date to Spanish format like 'LUNES, 15 DE ENERO DEL 2025'"""
        try:
            # Parse the date string (assuming YYYY-MM-DD format)
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            
            # Spanish day names
            dias = ['LUNES', 'MARTES', 'MIÉRCOLES', 'JUEVES', 'VIERNES', 'SÁBADO', 'DOMINGO']
            # Spanish month names
            meses = ['ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 
                    'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE']
            
            dia_semana = dias[date_obj.weekday()]
            dia = date_obj.day
            mes = meses[date_obj.month - 1]
            anio = date_obj.year
            
            return f"{dia_semana}, {dia} DE {mes} DEL {anio}"
        except:
            return date_str
    
    def _extract_year_from_date(self, date_str):
        """Extract year from date string DD/MM/YYYY"""
        try:
            return date_str.split('/')[-1]
        except:
            return str(datetime.now().year)
    
    def generate_excel_report(self, desde, hasta):
        """Generate Excel report matching PHP script format"""
        try:
            # Get data
            report_data = self._get_report_data(desde, hasta)
            notary_name = self._get_notary_info()
            
            # Create workbook and worksheet
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "INDICE CRONOLOGICO CARTAS NOTARIALES"
            
            # Styles
            title_font = Font(size=18, bold=True)
            header_font = Font(size=13, bold=True)
            cell_font = Font(size=13)
            border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )
            center_alignment = Alignment(horizontal='center', vertical='center')
            left_alignment = Alignment(horizontal='left', vertical='top')
            
            # Header section
            ws.merge_cells('A1:F1')
            ws['A1'] = 'INDICE CRONOLOGICO - CARTAS NOTARIALES'
            ws['A1'].font = title_font
            ws['A1'].alignment = center_alignment
            
            # Year
            anio = self._extract_year_from_date(hasta)
            ws.merge_cells('A2:F2')
            ws['A2'] = f'AÑO {anio}'
            ws['A2'].font = title_font
            ws['A2'].alignment = center_alignment
            
            # Notary info section
            row = 4
            ws.merge_cells(f'A{row}:B{row}')
            ws[f'A{row}'] = 'NOTARIA'
            ws[f'A{row}'].font = header_font
            ws[f'C{row}'] = f': {notary_name}'
            ws[f'C{row}'].font = cell_font
            
            row += 1
            ws.merge_cells(f'A{row}:B{row}')
            ws[f'A{row}'] = 'DIRECCION'
            ws[f'A{row}'].font = header_font
            ws[f'C{row}'] = ': JR.BOLIVAR NRO. 340'
            ws[f'C{row}'].font = cell_font
            ws[f'D{row}'] = 'TELEFONO'
            ws[f'D{row}'].font = header_font
            ws.merge_cells(f'E{row}:F{row}')
            ws[f'E{row}'] = ': (051) 326609'
            ws[f'E{row}'].font = cell_font
            
            row += 1
            ws.merge_cells(f'A{row}:B{row}')
            ws[f'A{row}'] = 'DEPARTAMENTO'
            ws[f'A{row}'].font = header_font
            ws[f'C{row}'] = ': PUNO'
            ws[f'C{row}'].font = cell_font
            ws[f'D{row}'] = 'RUC'
            ws[f'D{row}'].font = header_font
            ws.merge_cells(f'E{row}:F{row}')
            ws[f'E{row}'] = ': 10024231572'
            ws[f'E{row}'].font = cell_font
            
            row += 1
            ws.merge_cells(f'A{row}:B{row}')
            ws[f'A{row}'] = 'PROVINCIA'
            ws[f'A{row}'].font = header_font
            ws[f'C{row}'] = ': SAN ROMAN'
            ws[f'C{row}'].font = cell_font
            ws[f'D{row}'] = 'DESDE'
            ws[f'D{row}'].font = header_font
            ws.merge_cells(f'E{row}:F{row}')
            ws[f'E{row}'] = f': {self._format_date_in_spanish(desde)}'
            ws[f'E{row}'].font = cell_font
            
            row += 1
            ws.merge_cells(f'A{row}:B{row}')
            ws[f'A{row}'] = 'DISTRITO'
            ws[f'A{row}'].font = header_font
            ws[f'C{row}'] = ': JULIACA'
            ws[f'C{row}'].font = cell_font
            ws[f'D{row}'] = 'HASTA'
            ws[f'D{row}'].font = header_font
            ws.merge_cells(f'E{row}:F{row}')
            ws[f'E{row}'] = f': {self._format_date_in_spanish(hasta)}'
            ws[f'E{row}'].font = cell_font
            
            # Table headers
            row += 2
            headers = ['NRO', 'FEC. INGRESO', 'DIRECCION ENTREGA', 'FEC. ENTREGA', 'RESULTADO', 'FIRMO']
            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=row, column=col, value=header)
                cell.font = header_font
                cell.alignment = center_alignment
                cell.border = border
            
            # Data rows
            row += 1
            for data_row in report_data:
                # Main data row
                num_carta = data_row[0]
                fec_ingreso = data_row[1] or ''
                fec_entrega = data_row[2] or ''
                dir_destinatario = data_row[7] or ''
                recepcion = data_row[11] or ''
                firmo = data_row[12] or ''
                
                # Extract correlative number (remove year prefix)
                correlativo = str(num_carta)[-6:] if num_carta else ''
                
                # Row 1: Main data
                ws.cell(row=row, column=1, value=correlativo).font = cell_font
                ws.cell(row=row, column=2, value=fec_ingreso).font = cell_font
                ws.cell(row=row, column=3, value=dir_destinatario.upper()).font = cell_font
                ws.cell(row=row, column=4, value=fec_entrega).font = cell_font
                ws.cell(row=row, column=5, value=recepcion.upper()).font = cell_font
                ws.cell(row=row, column=6, value=firmo.upper()).font = cell_font
                
                # Apply borders to main row
                for col in range(1, 7):
                    ws.cell(row=row, column=col).border = border
                    ws.cell(row=row, column=col).alignment = center_alignment
                
                # Row 2: Additional info
                row += 1
                remitente = data_row[5] or ''
                destinatario = data_row[4] or ''
                dni_remitente = data_row[8] or ''
                dni_destinatario = data_row[9] or ''
                
                ws.cell(row=row, column=1, value='').font = cell_font
                ws.cell(row=row, column=2, value='REMITENTE:\nDESTINATARIO:').font = cell_font
                ws.merge_cells(f'C{row}:D{row}')
                ws.cell(row=row, column=3, value=f'{remitente}\n{destinatario}').font = cell_font
                ws.cell(row=row, column=5, value=f'DNI: {dni_remitente}\nDNI: {dni_destinatario}').font = cell_font
                ws.cell(row=row, column=6, value='').font = cell_font
                
                # Apply borders to info row
                for col in range(1, 7):
                    ws.cell(row=row, column=col).border = border
                    if col == 2:
                        ws.cell(row=row, column=col).alignment = center_alignment
                    elif col in [3, 5]:
                        ws.cell(row=row, column=col).alignment = left_alignment
                    else:
                        ws.cell(row=row, column=col).alignment = center_alignment
                
                row += 1
            
            # Auto-adjust column widths
            for column in ws.columns:
                max_length = 0
                column_letter = get_column_letter(column[0].column)
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                ws.column_dimensions[column_letter].width = adjusted_width
            
            # Save to BytesIO
            output = BytesIO()
            wb.save(output)
            output.seek(0)
            
            # Create HTTP response
            filename = f"INDICE_CRONOLOGICO_CARTAS_NOTARIALES_{anio}.xlsx"
            response = HttpResponse(
                output.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
            
        except Exception as e:
            return Response(
                {'error': f'Error generating Excel report: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def generate_word_report(self, desde, hasta):
        """Generate Word report matching PHP script format"""
        try:
            # Get data
            report_data = self._get_report_data(desde, hasta)
            notary_name = self._get_notary_info()
            
            # Create a new document
            from docx import Document
            from docx.shared import Inches, Pt
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.oxml.shared import OxmlElement, qn
            
            doc = Document()
            
            # Set margins
            sections = doc.sections
            for section in sections:
                section.top_margin = Inches(0.5)
                section.bottom_margin = Inches(0.5)
                section.left_margin = Inches(0.5)
                section.right_margin = Inches(0.5)
            
            # Title
            title = doc.add_heading('INDICE CRONOLOGICO - CARTAS NOTARIALES', 0)
            title.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            # Year
            anio = self._extract_year_from_date(hasta)
            year_heading = doc.add_heading(f'AÑO {anio}', 0)
            year_heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            # Add spacing
            doc.add_paragraph()
            doc.add_paragraph()
            
            # Notary info table
            info_table = doc.add_table(rows=5, cols=6)
            info_table.style = 'Table Grid'
            
            # Row 1: NOTARIA
            row = info_table.rows[0]
            row.cells[0].merge(row.cells[1])
            row.cells[0].text = 'NOTARIA'
            row.cells[2].text = f': {notary_name}'
            
            # Row 2: DIRECCION
            row = info_table.rows[1]
            row.cells[0].merge(row.cells[1])
            row.cells[0].text = 'DIRECCION'
            row.cells[2].text = ': JR.BOLIVAR NRO. 340'
            row.cells[3].text = 'TELEFONO'
            row.cells[4].merge(row.cells[5])
            row.cells[4].text = ': (051) 326609'
            
            # Row 3: DEPARTAMENTO
            row = info_table.rows[2]
            row.cells[0].merge(row.cells[1])
            row.cells[0].text = 'DEPARTAMENTO'
            row.cells[2].text = ': PUNO'
            row.cells[3].text = 'RUC'
            row.cells[4].merge(row.cells[5])
            row.cells[4].text = ': 10024231572'
            
            # Row 4: PROVINCIA
            row = info_table.rows[3]
            row.cells[0].merge(row.cells[1])
            row.cells[0].text = 'PROVINCIA'
            row.cells[2].text = ': SAN ROMAN'
            row.cells[3].text = 'DESDE'
            row.cells[4].merge(row.cells[5])
            row.cells[4].text = f': {self._format_date_in_spanish(desde)}'
            
            # Row 5: DISTRITO
            row = info_table.rows[4]
            row.cells[0].merge(row.cells[1])
            row.cells[0].text = 'DISTRITO'
            row.cells[2].text = ': JULIACA'
            row.cells[3].text = 'HASTA'
            row.cells[4].merge(row.cells[5])
            row.cells[4].text = f': {self._format_date_in_spanish(hasta)}'
            
            # Style the info table
            for row in info_table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        for run in paragraph.runs:
                            if ':' in run.text:
                                run.font.bold = True
                            run.font.size = Pt(12)
            
            # Add spacing
            doc.add_paragraph()
            
            # Main data table
            if report_data:
                # Create table with headers
                headers = ['NRO', 'FEC. INGRESO', 'DIRECCION ENTREGA', 'FEC. ENTREGA', 'RESULTADO', 'FIRMO']
                data_table = doc.add_table(rows=1, cols=6)
                data_table.style = 'Table Grid'
                
                # Add headers
                header_row = data_table.rows[0]
                for i, header in enumerate(headers):
                    cell = header_row.cells[i]
                    cell.text = header
                    for paragraph in cell.paragraphs:
                        for run in paragraph.runs:
                            run.font.bold = True
                            run.font.size = Pt(12)
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                
                # Add data rows
                for data_row in report_data:
                    num_carta = data_row[0]
                    fec_ingreso = data_row[1] or ''
                    fec_entrega = data_row[2] or ''
                    dir_destinatario = data_row[7] or ''
                    recepcion = data_row[11] or ''
                    firmo = data_row[12] or ''
                    
                    # Extract correlative number
                    correlativo = str(num_carta)[-6:] if num_carta else ''
                    
                    # Row 1: Main data
                    row = data_table.add_row()
                    row.cells[0].text = correlativo
                    row.cells[1].text = fec_ingreso
                    row.cells[2].text = dir_destinatario.upper()
                    row.cells[3].text = fec_entrega
                    row.cells[4].text = recepcion.upper()
                    row.cells[5].text = firmo.upper()
                    
                    # Center align main data
                    for i in range(6):
                        for paragraph in row.cells[i].paragraphs:
                            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    
                    # Row 2: Additional info
                    row = data_table.add_row()
                    remitente = data_row[5] or ''
                    destinatario = data_row[4] or ''
                    dni_remitente = data_row[8] or ''
                    dni_destinatario = data_row[9] or ''
                    
                    row.cells[0].text = ''
                    row.cells[1].text = 'REMITENTE:\nDESTINATARIO:'
                    row.cells[1].merge(row.cells[2])
                    row.cells[1].text = f'{remitente}\n{destinatario}'
                    row.cells[3].text = ''
                    row.cells[4].text = f'DNI: {dni_remitente}\nDNI: {dni_destinatario}'
                    row.cells[5].text = ''
                    
                    # Style the info row
                    for i in range(6):
                        if i == 1:  # REMITENTE/DESTINATARIO column
                            for paragraph in row.cells[i].paragraphs:
                                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        elif i == 3:  # DNI column
                            for paragraph in row.cells[i].paragraphs:
                                paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                        else:
                            for paragraph in row.cells[i].paragraphs:
                                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                
                # Style all cells
                for row in data_table.rows:
                    for cell in row.cells:
                        for paragraph in cell.paragraphs:
                            for run in paragraph.runs:
                                run.font.size = Pt(12)
            
            # Save to BytesIO
            output = BytesIO()
            doc.save(output)
            output.seek(0)
            
            # Create HTTP response
            filename = f"INDICE_CRONOLOGICO_CARTAS_NOTARIALES_{anio}.docx"
            response = HttpResponse(
                output.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
            
        except Exception as e:
            return Response(
                {'error': f'Error generating Word report: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )