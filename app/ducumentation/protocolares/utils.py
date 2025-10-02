from datetime import datetime
from decimal import Decimal
import locale
import boto3
from botocore.config import Config
import os
import re
from docx.shared import RGBColor


class NumberToLetterConverter:
    """
    Utility class to convert numbers and dates to letter format in Spanish
    """

    def __init__(self):
        # Set locale for Spanish date formatting
        try:
            locale.setlocale(locale.LC_TIME, "es_ES.UTF-8")
        except:
            try:
                locale.setlocale(locale.LC_TIME, "es_ES")
            except:
                print("WARNING: Spanish locale not available, falling back to default")

    def number_to_letters(self, number) -> str:
        """Convert number to words in Spanish"""
        try:
            number = int(number)
        except (ValueError, TypeError):
            print(f"WARNING: Invalid number value: {number}")
            return str(number)

        UNITS = ["", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE"]
        TENS = [
            "",
            "DIEZ",
            "VEINTE",
            "TREINTA",
            "CUARENTA",
            "CINCUENTA",
            "SESENTA",
            "SETENTA",
            "OCHENTA",
            "NOVENTA",
        ]
        TEENS = [
            "DIEZ",
            "ONCE",
            "DOCE",
            "TRECE",
            "CATORCE",
            "QUINCE",
            "DIECISEIS",
            "DIECISIETE",
            "DIECIOCHO",
            "DIECINUEVE",
        ]
        HUNDREDS = [
            "",
            "CIENTO",
            "DOSCIENTOS",
            "TRESCIENTOS",
            "CUATROCIENTOS",
            "QUINIENTOS",
            "SEISCIENTOS",
            "SETECIENTOS",
            "OCHOCIENTOS",
            "NOVECIENTOS",
        ]

        if number == 0:
            return "CERO"

        if number < 10:
            return UNITS[number]

        if number < 20:
            return TEENS[number - 10]

        if number < 100:
            tens = number // 10
            units = number % 10
            if units == 0:
                return TENS[tens]
            return f"{TENS[tens]} Y {UNITS[units]}"

        if number < 1000:
            hundreds = number // 100
            rest = number % 100
            if rest == 0:
                return HUNDREDS[hundreds]
            return f"{HUNDREDS[hundreds]} {self.number_to_letters(rest)}"

        if number < 1000000:
            thousands = number // 1000
            rest = number % 1000
            if thousands == 1:
                thousands_text = "MIL"
            else:
                thousands_text = self.number_to_letters(thousands) + " MIL"

            if rest == 0:
                return thousands_text
            return f"{thousands_text} {self.number_to_letters(rest)}"

        return str(number)

    def date_to_letters(self, date_str) -> str:
        """Convert date to words in Spanish"""
        if not date_str:
            print(f"WARNING: Empty date value")
            return ""

        try:
            if isinstance(date_str, str):
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            else:
                date_obj = date_str

            day = self.number_to_letters(date_obj.day)

            # Manual Spanish month names
            spanish_months = {
                1: "ENERO",
                2: "FEBRERO",
                3: "MARZO",
                4: "ABRIL",
                5: "MAYO",
                6: "JUNIO",
                7: "JULIO",
                8: "AGOSTO",
                9: "SEPTIEMBRE",
                10: "OCTUBRE",
                11: "NOVIEMBRE",
                12: "DICIEMBRE",
            }

            month = spanish_months[date_obj.month]
            year = self.number_to_letters(date_obj.year)

            return f"{day} DE {month} DEL {year}"
        except Exception as e:
            print(f"ERROR: Failed to convert date to letters: {e}")
            return str(date_str)

    def money_to_letters(self, currency: str, amount: Decimal) -> str:
        """Convert money amount to words in Spanish"""
        try:
            integer_part = int(amount)
            decimal_part = int((amount % 1) * 100)

            integer_text = self.number_to_letters(integer_part)
            decimal_text = self.number_to_letters(decimal_part)

            if currency == "SOLES":
                return f"{integer_text} SOLES CON {decimal_text} CÉNTIMOS"
            elif currency == "DOLARES N.A.":
                return f"{integer_text} DÓLARES AMERICANOS CON {decimal_text} CENTAVOS"
            else:
                return f"{integer_text} {currency} CON {decimal_text} CENTAVOS"
        except Exception as e:
            print(f"ERROR: Failed to convert money to letters: {e}")
            return f"{amount} {currency}"


# In utils.py - Add this class
class DocumentFormatter:
    """
    Format document data for templates
    Handles complex formatting logic that was in PHP
    """

    def __init__(self, letras_converter):
        self.letras = letras_converter

    def format_document_data(self, raw_data):
        """
        Format basic document data
        """
        print(f"DEBUG: Processing document data")

        numero_escritura = raw_data.get("numero_escritura") or ""
        fecha_escritura = raw_data.get("fecha_escritura")
        numero_minuta = raw_data.get("numero_minuta") or ""

        numero_acta = (
            f"{numero_escritura}({self.letras.number_to_letters(numero_escritura)})"
            if numero_escritura
            else "{{NRO_ESC}}"
        )
        fecha_impresion = (
            self.letras.date_to_letters(fecha_escritura) if fecha_escritura else "{{F_IMPRESION}}"
        )
        fecha_acta = self.letras.date_to_letters(fecha_escritura) if fecha_escritura else "{{F}}"
        numero_minuta_formatted = numero_minuta if numero_minuta else "{{NRO_MIN}}"

        return {
            "NRO_ESC": numero_acta,
            "K": raw_data.get("kardex", ""),
            "NUM_REG": "1",
            "FEC_LET": self.letras.date_to_letters(fecha_escritura) if fecha_escritura else "",
            "F_IMPRESION": fecha_impresion,
            "USUARIO": raw_data.get("usuario", ""),
            "USUARIO_DNI": raw_data.get("dni_usuario", ""),
            "NRO_MIN": numero_minuta_formatted,
            "COMPROBANTE": "sin",
            "O_S": raw_data.get("kardex", ""),
            "ORDEN_SERVICIO": raw_data.get("kardex", ""),
            "F": fecha_acta,
            "DESCRIPCION_SELLO": f"{raw_data.get('abogado', '')} PUNO {raw_data.get('matricula', '')}",
        }

    def format_contractor_data(self, raw_data):
        """
        Format contractor data into template-ready format
        Mirrors: PHP get_data_contratantes() complex logic

        SOLUTION:
        - Process transferentes and adquirientes
        - Handle gender-specific formatting
        - Generate P_NOM, C_NOM, etc. placeholders
        - Return flat dictionary for template replacement
        """
        # TODO: Implement contractor formatting logic
        # TODO: Handle married couples logic
        # TODO: Generate gender-specific text
        # TODO: Return flat dictionary with P_NOM, C_NOM, etc.
        pass

    def format_payment_data(self, raw_data):
        """
        Format payment data with sunat logic
        Mirrors: PHP get_data_pagos() switch statement
        """
        print(f"DEBUG: Processing payment data")

        # Extract payment data
        precio = raw_data.get("precio") or 0
        moneda = raw_data.get("descripcion_moneda") or "SOLES"
        simbolo_moneda = raw_data.get("simbolo_moneda") or "S/."
        sunat_medio_pago = raw_data.get("sunat_medio_pago") or "008"

        # Convert amount to letters
        monto_letras = self.letras.money_to_letters(moneda, Decimal(str(precio)))

        # Handle sunat_medio_pago logic (switch statement from PHP)
        if sunat_medio_pago == "008":
            medio_pago = 'EL COMPRADOR DECLARA QUE HA PAGADO EL PRECIO DEL VEHICULO EN DINERO EN EFECTIVO. NO HABIENDO UTILIZADO NINGÚN MEDIO DE PAGO ESTABLECIDO EN LA LEY Nº 28194, PORQUE EL MONTO TOTAL NO ES IGUAL NI SUPERA LOS S/ 3,500.00 O US$ 1,000.00. EL TIPO Y CÓDIGO DEL MEDIO EMPLEADO ES: "EFECTIVO POR OPERACIONES EN LAS QUE NO EXISTE OBLIGACIÓN DE UTILIZAR MEDIOS DE PAGO-008". INAPLICABLE LA LEY 30730 POR SER EL PAGO DEL PRECIO INFERIOR A 3 UIT.'
            exhibio_medio_pago = "SE DEJA CONSTANCIA QUE PARA LA REALIZACIÓN DEL PRESENTE ACTO, LAS PARTES NO ME HAN EXHIBIDO NINGÚN MEDIO DE PAGO. DOY FE."
            fin_medio_pago = "EN DINERO EN EFECTIVO"
            forma_pago = "AL CONTADO CON DINERO EN EFECTIVO"
        elif sunat_medio_pago == "009":
            medio_pago = 'EL COMPRADOR DECLARA QUE HA PAGADO EL PRECIO DEL VEHICULO EN DINERO EN EFECTIVO Y CON ANTERIORIDAD A LA CELEBRACION DE LA PRESENTE ACTA DE TRANSFERENCIA. NO HABIENDO UTILIZADO NINGÚN MEDIO DE PAGO ESTABLECIDO EN LA LEY Nº 28194, EL TIPO Y CÓDIGO DEL MEDIO EMPLEADO ES: "EFECTIVO POR OPERACIONES EN LAS QUE NO EXISTE OBLIGACIÓN DE UTILIZAR MEDIOS DE PAGO-009". INAPLICABLE LA LEY 30730 POR SER EL PAGO DEL PRECIO INFERIOR A 3 UIT.'
            exhibio_medio_pago = "SE DEJA CONSTANCIA QUE PARA LA REALIZACIÓN DEL PRESENTE ACTO, LAS PARTES NO ME HAN EXHIBIDO NINGÚN MEDIO DE PAGO. DOY FE."
            fin_medio_pago = "EN DINERO EN EFECTIVO"
            forma_pago = "AL CONTADO CON DINERO EN EFECTIVO"
        else:
            medio_pago = 'EL COMPRADOR DECLARA QUE HA PAGADO EL PRECIO DEL VEHICULO CON CHEQUE DEL BANCO DE CREDITO DEL PERÚ N° 1111111 111111 1111, GIRADO POR: YYYYYYYYY A FAVOR DE: XXXXXXXXX POR LA SUMA DE S/ 15,000.00, JULIACA 16/08/2018 EL TIPO Y CÓDIGO DEL MEDIO EMPLEADO ES: "CHEQUE -001" '
            exhibio_medio_pago = "EN APLICACIÓN DE LA LEY 30730, SE DEJA CONSTANCIA QUE PARA LA REALIZACIÓN DEL PRESENTE ACTO, LAS PARTES ME HAN EXHIBIDO EL SIGUIENTE MEDIO DE PAGO: ……… CHEQUE DEL BANCO DE CREDITO DEL PERÚ N° 1111111 111111 1111, GIRADO POR: YYYYYYYYY A FAVOR DE: XXXXXXXXX POR LA SUMA DE S/ 15,000.00, JULIACA 16/08/2018. DOY FE."
            fin_medio_pago = "EN DINERO EN EFECTIVO"
            forma_pago = "AL CONTADO CON DINERO EN EFECTIVO"

        return {
            "MONTO": str(precio),
            "MON_VEHI": moneda,
            "MONTO_LETRAS": monto_letras,
            "MONEDA_C": f"{simbolo_moneda} ",
            "SUNAT_MED_PAGO": sunat_medio_pago,
            "DES_PRE_VEHI": monto_letras,
            "EXH_MED_PAGO": exhibio_medio_pago,
            "MED_PAGO": medio_pago,
            "FIN_MED_PAGO": fin_medio_pago,
            "FORMA_PAGO": forma_pago,
            "C_INICIO_MP": "",
            "TIPO_PAGO_E": "",
            "TIPO_PAGO_C": "",
            "MONTO_MP": "",
            "CONSTANCIA": "",
            "DETALLE_MP": "",
            "FORMA_PAGO_S": "",
            "MONEDA_C_MP": "",
            "MEDIO_PAGO_C": "",
            "MP_MEDIO_PAGO": "",
            "MP_COMPLETO": "",
            "USO": "",
        }

    def format_vehicle_data(self, raw_data):
        """
        Format vehicle data
        Mirrors: PHP get_data_vehiculos()
        """
        print(f"DEBUG: Processing vehicle data")

        # Extract sede registral and parse it
        sede = raw_data.get("sede") or ""
        sede_parts = sede.split("-") if sede else ["", ""]
        sede_name = sede_parts[1].strip() if len(sede_parts) > 1 else ""

        return {
            "PLACA": str(raw_data.get("placa") or "").upper(),
            "CLASE": str(raw_data.get("clase") or "").upper(),
            "MARCA": str(raw_data.get("marca") or "").upper(),
            "MODELO": str(raw_data.get("modelo") or "").upper(),
            "AÑO_FABRICACION": str(raw_data.get("anio") or "").upper(),
            "CARROCERIA": str(raw_data.get("carroceria") or "").upper(),
            "COLOR": str(raw_data.get("color") or "").upper(),
            "NRO_MOTOR": str(raw_data.get("motor") or "").upper(),
            "NRO_SERIE": str(raw_data.get("serie") or "").upper(),
            "FEC_INS": str(raw_data.get("fecha_inscripcion") or "").upper(),
            "FECHA_INSCRIPCION": str(raw_data.get("fecha_inscripcion") or "").upper(),
            "ZONA_REGISTRAL": str(sede).upper(),
            "NUM_ZONA_REG": str(raw_data.get("numero_zona") or "").upper(),
            "SEDE": str(sede_name).upper(),
            "INSTRUIDO": " ",
            "COMBUSTIBLE": " ",
            "NRO_TARJETA": " ",
        }

    def format_escrituracion_data(self, raw_data):
        """
        Format escrituracion data (folio and papel numbers)
        """
        print(f"DEBUG: Processing escrituracion data")

        folio_inicial = raw_data.get("folio_inicial") or ""
        folio_final = raw_data.get("folio_final") or ""
        papel_inicial = raw_data.get("papel_inicial") or ""
        papel_final = raw_data.get("papel_final") or ""

        return {
            "FI": folio_inicial if folio_inicial else "{{FI}}",
            "S_IN": papel_inicial if papel_inicial else "{{S_IN}}",
            "FF": folio_final if folio_final else "{{FF}}",
            "S_FN": papel_final if papel_final else "{{S_FN}}",
        }

    def combine_all_data(
        self,
        data_documento,
        data_vehiculos,
        data_pagos,
        data_escrituracion,
        # data_contratantes,
    ):
        """
        Combine all data dictionaries into one
        Mirrors: PHP array merging with +=
        """
        print(f"DEBUG: Combining all data")
        # Merge all dictionaries
        final_data = {
            **data_documento,
            **data_vehiculos,
            **data_pagos,
            **data_escrituracion,
        }

        # TODO: Add contractor data when implemented
        # if data_contratantes:
        #     final_data.update(data_contratantes)

        return final_data


# In utils.py - Add this class
class PlaceholderProcessor:
    """
    Handle placeholder replacement in Word documents
    Preserves formatting while replacing text
    """

    def replace_placeholders(self, doc, final_data):
        """
        Replace {{PLACEHOLDERS}} in Word document
        Mirrors: PHP template processing
        """
        print(f"DEBUG: Replacing placeholders")

        # Replace in paragraphs
        for i, paragraph in enumerate(doc.paragraphs):
            if "{{" in paragraph.text and "}}" in paragraph.text:
                self._replace_in_paragraph(paragraph, final_data)

        # Replace in tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        if "{{" in paragraph.text and "}}" in paragraph.text:
                            self._replace_in_paragraph(paragraph, final_data)

        print(f"DEBUG: Placeholder replacement completed")

    def _replace_in_paragraph(self, paragraph, final_data):
        """
        Replace placeholders in a paragraph while preserving formatting
        Only replaced values will be BOLD and RED, not the entire paragraph
        """
        full_text = paragraph.text

        # Quick check - if no placeholders, skip
        if "{{" not in full_text or "}}" not in full_text:
            return

        # Track which placeholders we've already replaced
        replaced_placeholders = set()

        # Try simple replacement first (works if placeholder is in one run)
        for key, value in final_data.items():
            placeholder = f"{{{{{key}}}}}"

            if placeholder in full_text and placeholder not in replaced_placeholders:
                # Try to find and replace in individual runs
                for run in paragraph.runs:
                    if placeholder in run.text:
                        run.text = run.text.replace(placeholder, str(value))

                        # Apply bold and red formatting to the replaced text
                        run.font.bold = True
                        run.font.color.rgb = RGBColor(255, 0, 0)  # Red color

                        replaced_placeholders.add(placeholder)
                        break  # Move to next placeholder, don't return!

        # If we get here, some placeholders might be split across runs
        # Fall back to paragraph-level replacement for remaining placeholders
        remaining_placeholders = []
        for key, value in final_data.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in full_text and placeholder not in replaced_placeholders:
                remaining_placeholders.append((placeholder, str(value)))

        if remaining_placeholders:
            # Get the formatting from the first run
            first_run_font = None
            if paragraph.runs:
                first_run_font = paragraph.runs[0].font

            # Clear all runs
            for run in paragraph.runs:
                run.text = ""

            # Create a pattern to match all remaining placeholders
            pattern_parts = []
            replacements = {}

            for placeholder, value in remaining_placeholders:
                # Escape special regex characters in placeholder
                escaped_placeholder = re.escape(placeholder)
                pattern_parts.append(escaped_placeholder)
                replacements[placeholder] = value

            # Create regex pattern
            pattern = "|".join(pattern_parts)

            # Split text by placeholders and create separate runs
            parts = re.split(f"({pattern})", full_text)

            for part in parts:
                if part in replacements:
                    # This is a placeholder - create formatted run
                    new_run = paragraph.add_run(replacements[part])
                    new_run.font.bold = True
                    new_run.font.color.rgb = RGBColor(255, 0, 0)  # Red color

                    # Preserve font size and name from original
                    if first_run_font:
                        try:
                            new_run.font.size = first_run_font.size
                            new_run.font.name = first_run_font.name
                        except:
                            pass

                elif part:  # Only create run if text is not empty
                    # This is regular text - preserve original formatting
                    new_run = paragraph.add_run(part)
                    if first_run_font:
                        try:
                            new_run.font.bold = first_run_font.bold
                            new_run.font.italic = first_run_font.italic
                            new_run.font.color.rgb = first_run_font.color.rgb
                            new_run.font.size = first_run_font.size  # ADD THIS LINE!
                            new_run.font.name = first_run_font.name  # ADD THIS LINE TOO!
                        except:
                            pass

    def clean_unfilled_placeholders(self, doc):
        """
        Remove or hide unfilled placeholders
        Mirrors: PHP placeholder cleanup

        SOLUTION:
        - Find remaining {{PLACEHOLDERS}}
        - Hide escrituracion placeholders (white color)
        - Remove other placeholders completely
        """
        # TODO: Implement placeholder cleanup
        # TODO: Hide escrituracion placeholders
        # TODO: Remove other placeholders
        pass


# In utils.py - Add this class
class DataValidator:
    """
    Validate data before processing
    Ensure data integrity and handle edge cases
    """

    def validate_raw_data(self, raw_data):
        """
        Validate raw data from database
        Check for required fields and data integrity

        SOLUTION:
        - Check required fields exist
        - Validate data types
        - Handle null/empty values
        - Return validation results
        """
        # TODO: Implement data validation
        # TODO: Check required fields
        # TODO: Validate data types
        # TODO: Handle edge cases
        pass

    def validate_template_data(self, final_data):
        """
        Validate final template data
        Ensure all placeholders have values

        SOLUTION:
        - Check for missing placeholders
        - Validate placeholder values
        - Handle empty values
        - Return validation results
        """
        # TODO: Implement template data validation
        # TODO: Check missing placeholders
        # TODO: Validate placeholder values
        # TODO: Handle empty values
        pass


# In utils.py - Add this class
class TemplateManager:
    """
    Handle template operations
    Download, process, and manage templates
    """

    def __init__(self):
        self.s3_client = None  # Will be set when needed

    def get_template_from_r2(self, template_id, filename):
        """
        Download template from R2 storage
        Mirrors: PHP template download
        """
        print(f"DEBUG: Downloading template from R2: {filename}")

        s3 = boto3.client(
            "s3",
            endpoint_url=os.environ.get("CLOUDFLARE_R2_ENDPOINT"),
            aws_access_key_id=os.environ.get("CLOUDFLARE_R2_ACCESS_KEY"),
            aws_secret_access_key=os.environ.get("CLOUDFLARE_R2_SECRET_KEY"),
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )

        object_key = f"rodriguez-zea/plantillas/{filename}"

        try:
            response = s3.get_object(Bucket=os.environ.get("CLOUDFLARE_R2_BUCKET"), Key=object_key)
            template_bytes = response["Body"].read()
            print(f"DEBUG: Template downloaded successfully: {len(template_bytes)} bytes")
            return template_bytes
        except Exception as e:
            print(f"ERROR: Failed to download template from R2: {e}")
            raise

    def upload_document_to_r2(self, doc, kardex):
        """
        Upload generated document to R2
        Mirrors: PHP document upload

        SOLUTION:
        - Save document to buffer
        - Upload to R2 with proper key
        - Handle errors gracefully
        - Return success status
        """
        # TODO: Implement document upload
        # TODO: Save document to buffer
        # TODO: Upload to R2
        # TODO: Handle errors
        pass
