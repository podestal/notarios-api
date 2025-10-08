from datetime import datetime
from decimal import Decimal
import locale
import boto3
from botocore.config import Config
import os
import re
import io
from docx.shared import RGBColor
from docxtpl import DocxTemplate


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
        """

        # Define role classifications
        TRANSFEROR_ROLES = {
            "VENDEDOR",
            "DONANTE",
            "PODERDANTE",
            "OTORGANTE",
            "REPRESENTANTE",
            "ANTICIPANTE",
            "ADJUDICANTE",
            "USUFRUCTUANTE",
            "TRANSFERENTE",
            "TITULAR",
            "MUTUANTE",
            "PROPIETARIO",
            "DEUDOR",
            "ASOCIANTE",
            "TRANSFERENTE / PROPIETARIO (VENDEDOR)",
            "APODERADO",
        }

        ACQUIRER_ROLES = {
            "COMPRADOR",
            "DONATARIO",
            "APODERADO",
            "ANTICIPADO",
            "ADJUDICATARIO",
            "USUFRUCTUARIO",
            "TESTIGO A RUEGO",
            "ADQUIRIENTE",
            "ACREEDOR",
            "OTORGADO",
            "MUTUATARIO",
            "BENEFICIARIA",
            "ASOCIADO",
            "ADQUIRENTE / BENEFICIARIO (COMPRADOR)",
            "REPRESENTANTE",
        }

        REPRESENTATIVE_ROLES = {"APODERADO", "REPRESENTANTE"}

        # Parse contractor data from raw_data
        contractors = self._parse_contractor_data(raw_data)

        # Classify contractors
        transferors = []
        acquirers = []
        transferor_companies = []
        acquirer_companies = []

        for contractor in contractors:
            if contractor["tipper"] == "J":  # Company
                # Companies are classified based on their representatives' roles
                if contractor["condicion_str"] in TRANSFEROR_ROLES:
                    transferor_companies.append(contractor)
                elif contractor["condicion_str"] in ACQUIRER_ROLES:
                    acquirer_companies.append(contractor)
            elif contractor["condicion_str"] in TRANSFEROR_ROLES:
                transferors.append(contractor)
            elif contractor["condicion_str"] in ACQUIRER_ROLES:
                acquirers.append(contractor)

        # Generate contractor placeholders
        contractor_data = {}

        # Process transferors (P_ prefix)
        for idx, t in enumerate(transferors, 1):
            # Apply gender agreement for nationality and civil status
            nacionalidad = self._apply_gender_to_word(t["nacionalidad"], t["sexo"])
            estado_civil = self._apply_gender_to_word(t["estadoCivil"], t["sexo"])
            
            contractor_data[f"P_NOM_{idx}"] = t["nombres"] + " "
            contractor_data[f"P_NACIONALIDAD_{idx}"] = nacionalidad + " "
            contractor_data[f"P_DOC_{idx}"] = self._get_identification_phrase(
                t["sexo"], t["tipoDocumento"], t["numeroDocumento"]
            ) + " "
            contractor_data[f"P_IDE_{idx}"] = " "
            contractor_data[f"P_OCUPACION_{idx}"] = t["ocupacion"] + " "
            contractor_data[f"P_ESTADO_CIVIL_{idx}"] = estado_civil + " "
            contractor_data[f"P_DOMICILIO_{idx}"] = "CON DOMICILIO EN " + t["direccion"] + " "

            # Add unnumbered versions for first person
            if idx == 1:
                contractor_data["P_NOM"] = t["nombres"] + " "
                contractor_data["P_NACIONALIDAD"] = nacionalidad + " "
                contractor_data["P_DOC"] = self._get_identification_phrase(
                    t["sexo"], t["tipoDocumento"], t["numeroDocumento"]
                ) + " "
                contractor_data["P_IDE"] = " "
                contractor_data["P_OCUPACION"] = t["ocupacion"] + " "
                contractor_data["P_ESTADO_CIVIL"] = estado_civil + " "
                contractor_data["P_DOMICILIO"] = "CON DOMICILIO EN " + t["direccion"] + " "
                # CALIDAD_P will be set by _get_articles_and_grammar method

        # Process acquirers (C_ prefix)
        for idx, c in enumerate(acquirers, 1):
            # Apply gender agreement for nationality and civil status
            nacionalidad = self._apply_gender_to_word(c["nacionalidad"], c["sexo"])
            estado_civil = self._apply_gender_to_word(c["estadoCivil"], c["sexo"])
            
            contractor_data[f"C_NOM_{idx}"] = c["nombres"] + " "
            contractor_data[f"C_NACIONALIDAD_{idx}"] = nacionalidad + " "
            contractor_data[f"C_DOC_{idx}"] = self._get_identification_phrase(
                c["sexo"], c["tipoDocumento"], c["numeroDocumento"]
            ) + " "
            contractor_data[f"C_IDE_{idx}"] = " "
            contractor_data[f"C_OCUPACION_{idx}"] = c["ocupacion"] + " "
            contractor_data[f"C_ESTADO_CIVIL_{idx}"] = estado_civil + " "
            contractor_data[f"C_DOMICILIO_{idx}"] = "CON DOMICILIO EN " + c["direccion"] + " "

            # Add unnumbered versions for first person
            if idx == 1:
                contractor_data["C_NOM"] = c["nombres"] + " "
                contractor_data["C_NACIONALIDAD"] = nacionalidad + " "
                contractor_data["C_DOC"] = self._get_identification_phrase(
                    c["sexo"], c["tipoDocumento"], c["numeroDocumento"]
                ) + " "
                contractor_data["C_IDE"] = " "
                contractor_data["C_OCUPACION"] = c["ocupacion"] + " "
                contractor_data["C_ESTADO_CIVIL"] = estado_civil + " "
                contractor_data["C_DOMICILIO"] = "CON DOMICILIO EN " + c["direccion"] + " "
                # CALIDAD_C will be set by _get_articles_and_grammar method


        # Fill empty placeholders for unused slots
        self._fill_empty_contractor_placeholders(contractor_data, len(transferors), len(acquirers))
        self._fill_empty_company_placeholders(contractor_data, len(transferor_companies), len(acquirer_companies))

        # Add gender-based articles and grammar
        contractor_data.update(self._get_articles_and_grammar(transferors, "P"))
        contractor_data.update(self._get_articles_and_grammar(acquirers, "C"))
        
        # Add additional grammar placeholders
        contractor_data.update(self._get_additional_grammar(transferors, acquirers))

        return contractor_data

    def _parse_contractor_data(self, raw_data):
        """
        Parse contractor data from raw SQL query result
        """

        # Split comma-separated values from raw_data
        def split_if_not_none(value, separator=","):
            return value.split(separator) if value else []

        # Extract arrays from raw_data
        condiciones = split_if_not_none(raw_data.get("condicion"))
        nombres = split_if_not_none(raw_data.get("nombres"))
        nacionalidades = split_if_not_none(raw_data.get("nacionalidad"))
        tipos_documento = split_if_not_none(raw_data.get("tipo_documento"))
        numeros_documento = split_if_not_none(raw_data.get("numero_documento"))
        ocupaciones = split_if_not_none(raw_data.get("ocupacion"))
        estados_civil = split_if_not_none(raw_data.get("estado_civil"))
        direcciones = raw_data.get("direccion", "").split(",,") if raw_data.get("direccion") else []
        distritos = split_if_not_none(raw_data.get("distrito"))
        provincias = split_if_not_none(raw_data.get("provincia"))
        departamentos = split_if_not_none(raw_data.get("departamento"))
        sexos = split_if_not_none(raw_data.get("sexo"))
        id_clientes = split_if_not_none(raw_data.get("id_cliente"))
        id_conyuges = split_if_not_none(raw_data.get("id_conyuge"))
        
        # Company fields - use separate company fields from query
        razones_sociales = split_if_not_none(raw_data.get("nombre_empresa"))
        domicilios_fiscales = split_if_not_none(raw_data.get("domicilio_empresa"))
        tipos_persona_empresa = split_if_not_none(raw_data.get("tipo_persona_empresa"))
        condiciones_empresa = split_if_not_none(raw_data.get("condicion_empresa"))
        tipos_persona = split_if_not_none(raw_data.get("tipper"))

        contractors = []

        # Process each contractor
        for k, condicion in enumerate(condiciones):
            if not condicion:
                continue

            # Get data for this contractor
            nombre = nombres[k] if k < len(nombres) else ""
            nacionalidad = nacionalidades[k] if k < len(nacionalidades) else ""
            tipo_doc = tipos_documento[k] if k < len(tipos_documento) else ""
            num_doc = numeros_documento[k] if k < len(numeros_documento) else ""
            ocupacion = ocupaciones[k] if k < len(ocupaciones) else ""
            estado_civil = estados_civil[k] if k < len(estados_civil) else ""
            direccion = direcciones[k] if k < len(direcciones) else ""
            distrito = distritos[k] if k < len(distritos) else ""
            provincia = provincias[k] if k < len(provincias) else ""
            departamento = departamentos[k] if k < len(departamentos) else ""
            sexo = sexos[k] if k < len(sexos) else "M"
            id_cliente = id_clientes[k] if k < len(id_clientes) else ""
            id_conyuge = id_conyuges[k] if k < len(id_conyuges) else "NO"
            
            # Company data
            razon_social = razones_sociales[k] if k < len(razones_sociales) else ""
            domicilio_fiscal = domicilios_fiscales[k] if k < len(domicilios_fiscales) else ""
            tipper_empresa = tipos_persona_empresa[k] if k < len(tipos_persona_empresa) else ""
            condicion_empresa = condiciones_empresa[k] if k < len(condiciones_empresa) else ""
            tipper = tipos_persona[k] if k < len(tipos_persona) else "N"

            contractor = {
                "condiciones": condicion,
                "condicion_str": condicion,  # For role checking
                "nombres": nombre,
                "nacionalidad": nacionalidad,
                "tipoDocumento": tipo_doc,
                "numeroDocumento": num_doc,
                "ocupacion": ocupacion,
                "estadoCivil": estado_civil,
                "direccion": direccion,
                "distrito": distrito,
                "provincia": provincia,
                "departamento": departamento,
                "sexo": sexo,
                "idCliente": id_cliente,
                "idConyuge": id_conyuge,
                "tipper": tipper,  # N = Natural, J = Juridical
                # Company fields
                "razonsocial": razon_social,
                "domfiscal": domicilio_fiscal,
                "tipper_empresa": tipper_empresa,
                "condicion_empresa": condicion_empresa,
                "numdoc_empresa": num_doc if tipper == "J" else "",
            }

            contractors.append(contractor)

        return contractors

    def format_company_data(self, raw_data):
        """
        Format company data separately from contractors
        Companies are represented by juridical persons in the database
        """
        company_data = {}
        
        # Get company data from raw_data (handle None values)
        nombre_empresa = (raw_data.get("nombre_empresa") or "").strip().rstrip(',')
        domicilio_empresa = (raw_data.get("domicilio_empresa") or "").strip()
        tipo_persona_empresa = raw_data.get("tipo_persona_empresa") or ""
        condicion_empresa = (raw_data.get("condicion_empresa") or "").strip()
        numero_documento_empresa = (raw_data.get("numero_documento_empresa") or "").strip()
        numero_partida = (raw_data.get("numero_partida") or "").strip()
        distrito_empresa = (raw_data.get("distrito_empresa") or "").strip()
        provincia_empresa = (raw_data.get("provincia_empresa") or "").strip()
        departamento_empresa = (raw_data.get("departamento_empresa") or "").strip()
        oficina_registral = (raw_data.get("oficina_registral") or "").strip()
        
        # Process company data if it exists
        if nombre_empresa and tipo_persona_empresa == "J":
            # Determine which company slot to use based on condition
            if condicion_empresa in ['EMPRESA EN CONSTITUCION', 'ASOCIACION EN CONSTITUCION']:
                company_data["NOMBRE_EMPRESA_2"] = nombre_empresa
                company_data["INS_EMPRESA_2"] = f" INSCRITA EN LA PARTIDA ELECTRONICA N° {numero_partida} DE LA OFICINA REGISTRAL {oficina_registral}" if numero_partida else ""
                company_data["RUC_2"] = f", CON RUC N° {numero_documento_empresa}, " if numero_documento_empresa else ""
                company_data["DOMICILIO_EMPRESA_2"] = f"CON DOMICILIO EN {domicilio_empresa} DEL DISTRITO DE {distrito_empresa} PROVINCIA DE {provincia_empresa} Y DEPARTAMENTO DE {departamento_empresa}" if domicilio_empresa else ""
                company_data["CONDICION_EMPRESA_2"] = condicion_empresa
            else:
                company_data["NOMBRE_EMPRESA_1"] = nombre_empresa
                company_data["INS_EMPRESA_1"] = f" INSCRITA EN LA PARTIDA ELECTRONICA N° {numero_partida} DE LA OFICINA REGISTRAL {oficina_registral}" if numero_partida else ""
                company_data["RUC_1"] = f", CON RUC N° {numero_documento_empresa}, " if numero_documento_empresa else ""
                company_data["DOMICILIO_EMPRESA_1"] = f"CON DOMICILIO EN {domicilio_empresa} DEL DISTRITO DE {distrito_empresa} PROVINCIA DE {provincia_empresa} Y DEPARTAMENTO DE {departamento_empresa}" if domicilio_empresa else ""
                company_data["CONDICION_EMPRESA_1"] = condicion_empresa if condicion_empresa else ""
        
        # Fill empty company placeholders
        if "NOMBRE_EMPRESA_1" not in company_data:
            company_data["NOMBRE_EMPRESA_1"] = ""
            company_data["INS_EMPRESA_1"] = ""
            company_data["RUC_1"] = ""
            company_data["DOMICILIO_EMPRESA_1"] = ""
            company_data["CONDICION_EMPRESA_1"] = ""
        
        if "NOMBRE_EMPRESA_2" not in company_data:
            company_data["NOMBRE_EMPRESA_2"] = ""
            company_data["INS_EMPRESA_2"] = ""
            company_data["RUC_2"] = ""
            company_data["DOMICILIO_EMPRESA_2"] = ""
            company_data["CONDICION_EMPRESA_2"] = ""
        
        return company_data

    def _apply_gender_to_word(self, word, gender):
        """
        Apply gender agreement to Spanish words
        Mirrors: PHP logic - changes last letter based on gender
        
        Examples:
        - PERUANO (M) -> PERUANO, PERUANO (F) -> PERUANA
        - SOLTERO (M) -> SOLTERO, SOLTERO (F) -> SOLTERA
        """
        if not word or not word.strip():
            return word
        
        word = word.strip()
        
        # For female, change last 'O' to 'A'
        if gender == "F":
            if word.endswith("O"):
                return word[:-1] + "A"
        # For male, ensure it ends with 'O' (if it ended with 'A', change it)
        elif gender == "M":
            if word.endswith("A"):
                return word[:-1] + "O"
        
        return word
    
    def _get_identification_phrase(self, gender, doc_type, doc_number):
        """
        Generate identification phrase based on gender and document type
        """
        if not doc_number:
            return ""

        if gender == "F":
            return f"IDENTIFICADA CON {doc_type} N° {doc_number}"
        else:
            return f"IDENTIFICADO CON {doc_type} N° {doc_number}"

    def _fill_empty_contractor_placeholders(self, contractor_data, num_transferors, num_acquirers):
        """
        Fill empty placeholders for unused contractor slots
        """
        # Fill empty transferor slots (P_ prefix) - use empty strings, not [E.PLACEHOLDER]
        for idx in range(num_transferors + 1, 11):
            contractor_data[f"P_NOM_{idx}"] = ""  # Empty string instead of [E.P_NOM_X]
            contractor_data[f"P_NACIONALIDAD_{idx}"] = ""
            contractor_data[f"P_DOC_{idx}"] = ""
            contractor_data[f"P_IDE_{idx}"] = ""
            contractor_data[f"P_OCUPACION_{idx}"] = ""
            contractor_data[f"P_ESTADO_CIVIL_{idx}"] = ""
            contractor_data[f"P_DOMICILIO_{idx}"] = ""

        # Fill empty acquirer slots (C_ prefix) - use empty strings, not [E.PLACEHOLDER]
        for idx in range(num_acquirers + 1, 11):
            contractor_data[f"C_NOM_{idx}"] = ""  # Empty string instead of [E.C_NOM_X]
            contractor_data[f"C_NACIONALIDAD_{idx}"] = ""
            contractor_data[f"C_DOC_{idx}"] = ""
            contractor_data[f"C_IDE_{idx}"] = ""
            contractor_data[f"C_OCUPACION_{idx}"] = ""
            contractor_data[f"C_ESTADO_CIVIL_{idx}"] = ""
            contractor_data[f"C_DOMICILIO_{idx}"] = ""

    def _fill_empty_company_placeholders(self, contractor_data, num_transferor_companies, num_acquirer_companies):
        """
        Fill empty placeholders for unused company slots
        """
        total_companies = num_transferor_companies + num_acquirer_companies
        
        # Fill empty company slots - use empty strings, not [E.PLACEHOLDER]
        for idx in range(total_companies + 1, 6):  # Support up to 5 companies
            contractor_data[f"NOMBRE_EMPRESA_{idx}"] = ""
            contractor_data[f"INS_EMPRESA_{idx}"] = ""
            contractor_data[f"RUC_{idx}"] = ""
            contractor_data[f"DOMICILIO_EMPRESA_{idx}"] = ""

    def _get_articles_and_grammar(self, contractors, role_prefix):
        """
        Generate gender-based articles and grammar
        Mirrors: PHP articulos_singular_plural() function
        """
        if not contractors:
            return {}
        
        # Determine gender and number
        genders = [c.get("sexo", "M") for c in contractors]
        num_contractors = len(contractors)
        
        # Determine if all women (for proper grammar)
        all_women = all(g == "F" for g in genders)
        
        # Generate articles based on gender and number
        articles = {}
        
        if num_contractors >= 2:
            # PLURAL - Based on PHP logic
            if all_women:
                articles[f"EL_{role_prefix}"] = "LAS"
                articles[f"INICIO_{role_prefix}"] = "SEÑORAS"
                # Set CALIDAD based on role and gender
                if role_prefix == "P":
                    articles[f"CALIDAD_{role_prefix}"] = "VENDEDORAS"
                else:
                    articles[f"CALIDAD_{role_prefix}"] = "COMPRADORAS"
            else:
                articles[f"EL_{role_prefix}"] = "LOS"
                articles[f"INICIO_{role_prefix}"] = "SEÑORES"
                # Set CALIDAD based on role and gender
                if role_prefix == "P":
                    articles[f"CALIDAD_{role_prefix}"] = "VENDEDORES"
                else:
                    articles[f"CALIDAD_{role_prefix}"] = "COMPRADORES"
            
            articles[f"ES_{role_prefix}"] = "ES"
            articles[f"S_{role_prefix}"] = "S"
            articles[f"ES_SON_{role_prefix}"] = "SON"
            articles[f"Y_CON_{role_prefix}"] = "Y"
            articles[f"N_{role_prefix}"] = "N"
            articles[f"Y_{role_prefix}"] = "Y"
            articles[f"L_{role_prefix}"] = "L"
            articles[f"O_A_{role_prefix}"] = "OS"
            articles[f"O_ERON_{role_prefix}"] = "ERON"
            articles[f"O_ARON_{role_prefix}"] = "ARON"
            articles[f"{role_prefix}_FIRMA"] = "FIRMAN EN"
            
        else:
            # SINGULAR - Based on PHP logic
            if all_women:
                articles[f"EL_{role_prefix}"] = "LA"
                articles[f"INICIO_{role_prefix}"] = "SEÑORA"
                # Set CALIDAD based on role and gender (covers multiple document types)
                if role_prefix == "P":
                    articles[f"CALIDAD_{role_prefix}"] = "VENDEDORA"
                else:
                    articles[f"CALIDAD_{role_prefix}"] = "COMPRADORA"
                # Female singular
                articles[f"O_A_{role_prefix}"] = "A"
                articles[f"O_ERON_{role_prefix}"] = "A"
                articles[f"O_ARON_{role_prefix}"] = "A"
            else:
                articles[f"EL_{role_prefix}"] = "EL"
                articles[f"INICIO_{role_prefix}"] = "SEÑOR"
                # Set CALIDAD based on role and gender (covers multiple document types)
                if role_prefix == "P":
                    articles[f"CALIDAD_{role_prefix}"] = "VENDEDOR"
                else:
                    articles[f"CALIDAD_{role_prefix}"] = "COMPRADOR"
                # Male singular
                articles[f"O_A_{role_prefix}"] = "O"
                articles[f"O_ERON_{role_prefix}"] = "O"
                articles[f"O_ARON_{role_prefix}"] = "O"
            
            articles[f"ES_{role_prefix}"] = ""
            articles[f"S_{role_prefix}"] = ""
            articles[f"ES_SON_{role_prefix}"] = "ES"
            articles[f"Y_CON_{role_prefix}"] = ""
            articles[f"N_{role_prefix}"] = ""
            articles[f"Y_{role_prefix}"] = ""
            articles[f"L_{role_prefix}"] = ""
            articles[f"{role_prefix}_FIRMA"] = "FIRMA EN"
            articles[f"{role_prefix}_AMBOS"] = " "
        
        # Add spaces for proper formatting
        for key, value in articles.items():
            articles[key] = value + " "
        
        return articles

    def _get_additional_grammar(self, transferors, acquirers):
        """
        Generate additional grammar placeholders commonly used in notary documents
        """
        grammar = {}
        
        # Determine if we have multiple parties
        has_multiple_transferors = len(transferors) > 1
        has_multiple_acquirers = len(acquirers) > 1
        
        # Articles for multiple parties
        if has_multiple_transferors:
            grammar["LOS_P"] = "LOS "
            grammar["LAS_P"] = "LAS "
        else:
            grammar["LOS_P"] = "EL "
            grammar["LAS_P"] = "LA "
        
        if has_multiple_acquirers:
            grammar["LOS_C"] = "LOS "
            grammar["LAS_C"] = "LAS "
        else:
            grammar["LOS_C"] = "EL "
            grammar["LAS_C"] = "LA "
        
        # Conjunctions
        grammar["Y"] = "Y "
        grammar["O"] = "O "
        
        # Prepositions
        grammar["DE"] = "DE "
        grammar["A"] = "A "
        grammar["EN"] = "EN "
        grammar["POR"] = "POR "
        grammar["CON"] = "CON "
        
        # Common phrases
        grammar["QUE"] = "QUE "
        grammar["QUIEN"] = "QUIEN "
        grammar["QUIENES"] = "QUIENES "
        grammar["CUYO"] = "CUYO "
        grammar["CUYA"] = "CUYA "
        grammar["CUYOS"] = "CUYOS "
        grammar["CUYAS"] = "CUYAS "
        
        return grammar

    def format_payment_data(self, raw_data):
        """
        Format payment data with sunat logic
        Mirrors: PHP get_data_pagos() switch statement
        """

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
        data_contratantes,
        data_company=None,
    ):
        """
        Combine all data dictionaries into one
        Mirrors: PHP array merging with +=
        """
        # Merge all dictionaries
        final_data = {
            **data_documento,
            **data_vehiculos,
            **data_pagos,
            **data_escrituracion,
            **data_contratantes,
        }
        
        # Add company data if provided
        if data_company:
            final_data.update(data_company)

        return final_data


# In utils.py - Add this class
class DocxTemplateProcessor:
    """
    Handle placeholder replacement using python-docx-template
    This library is specifically designed for template processing with formatting
    """
    
    def replace_placeholders(self, template_bytes, final_data):
        """
        Replace placeholders using python-docx-template
        This preserves formatting and handles colors better
        """
        try:
            # Load template from bytes
            template = DocxTemplate(io.BytesIO(template_bytes))
            
            # Render the template with data
            template.render(final_data)
            
            # Save to bytes
            output = io.BytesIO()
            template.save(output)
            output.seek(0)
            
            return output.getvalue()
        except Exception as e:
            print(f"ERROR: DocxTemplate processing failed: {e}")
            # Fallback to original method
            return None

# In utils.py - Add this class
class PlaceholderProcessor:
    """
    Handle placeholder replacement in Word documents
    Preserves formatting while replacing text
    """

    def replace_placeholders(self, doc, final_data):
        """
        Replace {{PLACEHOLDERS}} in Word document
        Processes: paragraphs, tables, headers, and footers
        """
        
        # Replace in main document paragraphs
        for paragraph in doc.paragraphs:
            if "{{" in paragraph.text and "}}" in paragraph.text:
                self._replace_in_paragraph(paragraph, final_data)

        # Replace in tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        if "{{" in paragraph.text and "}}" in paragraph.text:
                            self._replace_in_paragraph(paragraph, final_data)
        
        # Replace in headers
        for section in doc.sections:
            header = section.header
            for paragraph in header.paragraphs:
                if "{{" in paragraph.text and "}}" in paragraph.text:
                    self._replace_in_paragraph(paragraph, final_data)
            
            # Replace in header tables
            for table in header.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for paragraph in cell.paragraphs:
                            if "{{" in paragraph.text and "}}" in paragraph.text:
                                self._replace_in_paragraph(paragraph, final_data)
        
        # Replace in footers
        for section in doc.sections:
            footer = section.footer
            for paragraph in footer.paragraphs:
                if "{{" in paragraph.text and "}}" in paragraph.text:
                    self._replace_in_paragraph(paragraph, final_data)
            
            # Replace in footer tables
            for table in footer.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for paragraph in cell.paragraphs:
                            if "{{" in paragraph.text and "}}" in paragraph.text:
                                self._replace_in_paragraph(paragraph, final_data)



    def debug_placeholder_formatting(self, doc):
        """
        Debug method to check if placeholders were properly formatted
        This will print information about the formatting of replaced text
        """
        
        for i, paragraph in enumerate(doc.paragraphs):
            if paragraph.runs:
                for j, run in enumerate(paragraph.runs):
                    if run.text.strip():
                        is_bold = run.font.bold
                        
                        # Simple color detection
                        try:
                            color_rgb = run.font.color.rgb
                            if hasattr(color_rgb, 'rgb'):
                                color_rgb = color_rgb.rgb
                            elif isinstance(color_rgb, (tuple, list)) and len(color_rgb) >= 3:
                                color_rgb = tuple(color_rgb[:3])
                        except:
                            color_rgb = None
                        
                        is_red = (color_rgb == (255, 0, 0))
                        

    def _replace_in_paragraph(self, paragraph, final_data):
        """
        Replace placeholders in a paragraph while preserving formatting
        Only replaced values will be BOLD and RED, not the entire paragraph
        """
        full_text = paragraph.text

        # Quick check - if no placeholders, skip
        if "{{" not in full_text or "}}" not in full_text:
            return

        # Get original formatting from first run
        first_run_font = None
        if paragraph.runs:
            first_run_font = paragraph.runs[0].font

        # Find all placeholders in the text
        import re
        placeholder_pattern = r'\{\{([^}]+)\}\}'
        matches = list(re.finditer(placeholder_pattern, full_text))
        
        if not matches:
            return

        # Clear all runs
        for run in paragraph.runs:
            run.text = ""

        # Split text by placeholders and create separate runs
        last_end = 0
        
        # Process each placeholder match
        for match in matches:
            placeholder = match.group(0)  # Full placeholder like {{NOMBRE}}
            key = match.group(1)  # Just the key like NOMBRE
            start = match.start()
            end = match.end()

            # Add text before placeholder
            if start > last_end:
                text_before = full_text[last_end:start]
                if text_before:
                    new_run = paragraph.add_run(text_before)
                    if first_run_font:
                        try:
                            new_run.font.bold = first_run_font.bold
                            new_run.font.italic = first_run_font.italic
                            new_run.font.color.rgb = first_run_font.color.rgb
                            if first_run_font.size:
                                new_run.font.size = first_run_font.size
                            if first_run_font.name:
                                new_run.font.name = first_run_font.name
                        except:
                            pass

            # Add replaced placeholder with RED and BOLD formatting
            if key in final_data:
                value = str(final_data[key])
                new_run = paragraph.add_run(value)
                
                # Set bold first
                new_run.font.bold = True
                
                # Set RED color - use direct RGB
                new_run.font.color.rgb = RGBColor(255, 0, 0)
                
                # Preserve font size and name from original
                if first_run_font:
                    try:
                        if first_run_font.size:
                            new_run.font.size = first_run_font.size
                        if first_run_font.name:
                            new_run.font.name = first_run_font.name
                    except:
                        pass
            else:
                # Placeholder not found in data, keep original placeholder
                new_run = paragraph.add_run(placeholder)
                if first_run_font:
                    try:
                        new_run.font.bold = first_run_font.bold
                        new_run.font.italic = first_run_font.italic
                        new_run.font.color.rgb = first_run_font.color.rgb
                        if first_run_font.size:
                            new_run.font.size = first_run_font.size
                        if first_run_font.name:
                            new_run.font.name = first_run_font.name
                    except:
                        pass
            
            last_end = end

        # Add remaining text after last placeholder
        if last_end < len(full_text):
            text_after = full_text[last_end:]
            if text_after:
                new_run = paragraph.add_run(text_after)
                if first_run_font:
                    try:
                        new_run.font.bold = first_run_font.bold
                        new_run.font.italic = first_run_font.italic
                        new_run.font.color.rgb = first_run_font.color.rgb
                        if first_run_font.size:
                            new_run.font.size = first_run_font.size
                        if first_run_font.name:
                            new_run.font.name = first_run_font.name
                    except:
                        pass

    def clean_unfilled_placeholders(self, doc):
        """
        Remove or hide unfilled placeholders
        Mirrors: PHP placeholder cleanup
        """

        # Define placeholder categories
        escrituracion_placeholders = {
            "{{FI}}",
            "{{FF}}",
            "{{S_IN}}",
            "{{S_FN}}",
            "{{NRO_ESC}}",
            "{{F}}",
            "{{F_IMPRESION}}",
        }

        contractor_placeholders = {
            "{{P_NOM}}",
            "{{P_NOM_2}}",
            "{{P_NOM_3}}",
            "{{P_NOM_4}}",
            "{{P_NOM_5}}",
            "{{C_NOM}}",
            "{{C_NOM_2}}",
            "{{C_NOM_3}}",
            "{{C_NOM_4}}",
            "{{C_NOM_5}}",
            "{{P_DOC}}",
            "{{P_DOC_2}}",
            "{{P_DOC_3}}",
            "{{P_DOC_4}}",
            "{{P_DOC_5}}",
            "{{C_DOC}}",
            "{{C_DOC_2}}",
            "{{C_DOC_3}}",
            "{{C_DOC_4}}",
            "{{C_DOC_5}}",
            "{{P_NACIONALIDAD}}",
            "{{P_NACIONALIDAD_2}}",
            "{{P_NACIONALIDAD_3}}",
            "{{P_NACIONALIDAD_4}}",
            "{{P_NACIONALIDAD_5}}",
            "{{C_NACIONALIDAD}}",
            "{{C_NACIONALIDAD_2}}",
            "{{C_NACIONALIDAD_3}}",
            "{{C_NACIONALIDAD_4}}",
            "{{C_NACIONALIDAD_5}}",
            "{{P_OCUPACION}}",
            "{{P_OCUPACION_2}}",
            "{{P_OCUPACION_3}}",
            "{{P_OCUPACION_4}}",
            "{{P_OCUPACION_5}}",
            "{{C_OCUPACION}}",
            "{{C_OCUPACION_2}}",
            "{{C_OCUPACION_3}}",
            "{{C_OCUPACION_4}}",
            "{{C_OCUPACION_5}}",
            "{{P_ESTADO_CIVIL}}",
            "{{P_ESTADO_CIVIL_2}}",
            "{{P_ESTADO_CIVIL_3}}",
            "{{P_ESTADO_CIVIL_4}}",
            "{{P_ESTADO_CIVIL_5}}",
            "{{C_ESTADO_CIVIL}}",
            "{{C_ESTADO_CIVIL_2}}",
            "{{C_ESTADO_CIVIL_3}}",
            "{{C_ESTADO_CIVIL_4}}",
            "{{C_ESTADO_CIVIL_5}}",
            "{{P_DOMICILIO}}",
            "{{P_DOMICILIO_2}}",
            "{{P_DOMICILIO_3}}",
            "{{P_DOMICILIO_4}}",
            "{{P_DOMICILIO_5}}",
            "{{C_DOMICILIO}}",
            "{{C_DOMICILIO_2}}",
            "{{C_DOMICILIO_3}}",
            "{{C_DOMICILIO_4}}",
            "{{C_DOMICILIO_5}}",
            "{{P_IDE}}",
            "{{P_IDE_2}}",
            "{{P_IDE_3}}",
            "{{P_IDE_4}}",
            "{{P_IDE_5}}",
            "{{C_IDE}}",
            "{{C_IDE_2}}",
            "{{C_IDE_3}}",
            "{{C_IDE_4}}",
            "{{C_IDE_5}}",
        }

        # Clean paragraphs
        for paragraph in doc.paragraphs:
            self._clean_paragraph_placeholders(
                paragraph, escrituracion_placeholders, contractor_placeholders
            )

        # Clean tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        self._clean_paragraph_placeholders(
                            paragraph, escrituracion_placeholders, contractor_placeholders
                        )


    def _clean_paragraph_placeholders(
        self, paragraph, escrituracion_placeholders, contractor_placeholders
    ):
        """
        Clean placeholders in a single paragraph - SIMPLIFIED VERSION
        """
        full_text = paragraph.text

        # Quick check - if no placeholders, skip
        if "{{" not in full_text and "[" not in full_text:
            return


        # Get original formatting
        first_run_font = None
        if paragraph.runs:
            first_run_font = paragraph.runs[0].font

        # Clear all runs
        for run in paragraph.runs:
            run.text = ""

        # Simple string replacement approach
        new_text = full_text

        # Remove both {{PLACEHOLDER}} and [E.PLACEHOLDER] formats
        import re

        # Remove {{PLACEHOLDER}} format
        new_text = re.sub(r"\{\{[^}]+\}\}", "", new_text)

        # Remove [E.PLACEHOLDER] format
        new_text = re.sub(r"\[E\.[^\]]+\]", "", new_text)


        # Clean up extra spaces and punctuation
        new_text = self._clean_text_formatting(new_text)

        # Create new run with cleaned text
        if new_text.strip():
            new_run = paragraph.add_run(new_text)

            # Preserve original formatting
            if first_run_font:
                try:
                    new_run.font.bold = first_run_font.bold
                    new_run.font.italic = first_run_font.italic
                    new_run.font.color.rgb = first_run_font.color.rgb
                    new_run.font.size = first_run_font.size
                    new_run.font.name = first_run_font.name
                except:
                    pass

    def _clean_text_formatting(self, text):
        """
        Clean up text formatting after placeholder removal
        """
        import re

        # Remove extra spaces
        text = re.sub(r"\s+", " ", text)

        # Remove extra commas and semicolons
        text = re.sub(r",\s*,", ",", text)
        text = re.sub(r";\s*;", ";", text)

        # Remove trailing commas and semicolons
        text = re.sub(r",\s*$", "", text)
        text = re.sub(r";\s*$", "", text)

        # Remove extra spaces around punctuation
        text = re.sub(r"\s+([,;.])", r"\1", text)

        # Remove empty contractor slots (multiple commas in a row)
        text = re.sub(r",\s*,", ",", text)  # Remove double commas
        text = re.sub(r",\s*,", ",", text)  # Remove triple commas

        # Remove leading/trailing commas
        text = re.sub(r"^,\s*", "", text)
        text = re.sub(r",\s*$", "", text)

        return text.strip()


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
