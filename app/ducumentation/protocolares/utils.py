from datetime import datetime
from decimal import Decimal
import locale
import boto3
from botocore.config import Config
import os


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

        THOUSANDS = [
            "",
            "MIL",
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
            if rest == 0:
                return THOUSANDS[thousands]
            return f"{THOUSANDS[thousands]} {self.number_to_letters(rest)}"

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
            month = date_obj.strftime("%B").upper()
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

        SOLUTION:
        - Handle sunat_medio_pago logic (008, 009, etc.)
        - Generate payment text based on method
        - Convert amounts to letters
        - Return MONTO, MONTO_LETRAS, MED_PAGO, etc.
        """
        # TODO: Implement payment formatting logic
        # TODO: Handle sunat_medio_pago switch
        # TODO: Generate payment method text
        # TODO: Return payment placeholders
        pass

    def format_vehicle_data(self, raw_data):
        """
        Format vehicle data
        Mirrors: PHP get_data_vehiculos()

        SOLUTION:
        - Extract vehicle fields
        - Convert to uppercase
        - Parse sede registral
        - Return PLACA, MARCA, MODELO, etc.
        """
        # TODO: Implement vehicle formatting logic
        # TODO: Handle sede registral parsing
        # TODO: Convert all to uppercase
        # TODO: Return vehicle placeholders
        pass

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

        SOLUTION:
        - Process all paragraphs
        - Process all tables
        - Use run-level replacement when possible
        - Fall back to paragraph-level when needed
        """
        # TODO: Implement placeholder replacement
        # TODO: Handle run-level replacement
        # TODO: Handle split placeholders
        # TODO: Preserve formatting
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
