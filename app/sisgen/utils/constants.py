"""
This module contains the constants for the sisgen service.
"""

import os
from typing import Dict, List

# SISGEN Service URLs
SISGEN_URLS = {
    'DOCUMENTS': os.getenv('SISGEN_DOCUMENTS_URL', 'https://servicios.notarios.org.pe/sisgen-web/DocumentosNotarialesService'),
    'BOOKS': os.getenv('SISGEN_BOOKS_URL', 'https://servicios.notarios.org.pe/sisgen-web/DocumentosLibrosService'),
}

# SISGEN Configuration
SISGEN_CONFIG = {
    'TIMEOUT': int(os.getenv('SISGEN_TIMEOUT', '500')),
    'VERIFY_SSL': os.getenv('SISGEN_VERIFY_SSL', 'false').lower() == 'true',
    'MAX_RETRIES': int(os.getenv('SISGEN_MAX_RETRIES', '3')),
}

# Database Configuration
DB_CONFIG = {
    'HOST': os.getenv('DB_HOST', 'db'),
    'USER': os.getenv('DB_USER', 'root'),
    'PASSWORD': os.getenv('DB_PASSWORD', '12345'),
    'NAME': os.getenv('DB_NAME', 'notarios'),
    'PORT': int(os.getenv('DB_PORT', '3306')),
}

# Application Constants
APP_CONSTANTS = {
    'APP_NAME': 'SISNOT',
    'APP_VERSION': '2.7',
    'PROVIDER_NAME': 'CNL',
    'MAX_SEARCH_RESULTS': int(os.getenv('MAX_SEARCH_RESULTS', '1000')),
    'DEFAULT_PAGE_SIZE': int(os.getenv('DEFAULT_PAGE_SIZE', '50')),
}

# Estado SISGEN Mapping
ESTADO_SISGEN_MAPPING = {
    0: 'No Enviado',
    1: 'Enviado',
    2: 'Enviado(Observado)',
    3: 'No Enviado(Fallido)',
    4: 'Sin Código ANCERT',
    5: 'Todos'
}

# Tipo Kardex SISGEN Mapping
TIPO_KARDEX_SISGEN_MAPPING = {
    1: 'E',  # Escritura
    2: 'C',  # Certificado
    3: 'V',  # Verificación
    4: 'G',  # Gestión
    5: 'T'   # Trámite
}

# Valid Estados
VALID_ESTADOS = [-1, 0, 1, 2, 3, 4, 5]

# Valid Tipos Instrumento
VALID_TIPOS_INSTRUMENTO = [1, 2, 3, 4, 5]

# Date Formats
DATE_FORMATS = ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d']

# XML Namespaces - Cross-platform compatible
XML_NAMESPACES = {
    'SISGEN': 'http://ancert.notariado.org/SISGEN/XML',
    'XSI': 'http://www.w3.org/2001/XMLSchema-instance',
    'SOAP': 'http://schemas.xmlsoap.org/soap/envelope/',
    'SISGEN_WS': 'http://ws.sisgen.ancert.notariado.org/'
}

# SOAP Headers
SOAP_HEADERS = {
    'Content-Type': 'text/xml;charset=utf-8',
    'Accept': 'text/xml',
    'Accept-Encoding': 'gzip',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
}

# Error Messages
ERROR_MESSAGES = {
    'MISSING_REQUIRED_FIELD': 'Missing required field: {field}',
    'INVALID_DATE_FORMAT': 'Invalid date format. Use YYYY-MM-DD',
    'INVALID_ESTADO': 'Invalid estado. Must be one of: {valid_estados}',
    'INVALID_TIPO_INSTRUMENTO': 'Invalid tipoInstrumento. Must be one of: {valid_tipos}',
    'DATE_RANGE_TOO_LARGE': 'Date range cannot exceed 1 year',
    'INVALID_DATE_RANGE': 'fechaDesde cannot be later than fechaHasta',
    'NO_DOCUMENTS_FOUND': 'No documents found for the specified criteria',
    'SISGEN_SERVICE_ERROR': 'SISGEN service error: {error}',
    'XML_GENERATION_ERROR': 'Error generating XML: {error}',
    'DATABASE_ERROR': 'Database error: {error}',
    'VALIDATION_ERROR': 'Validation error: {error}',
}

# Success Messages
SUCCESS_MESSAGES = {
    'DOCUMENTS_FOUND': 'Documents found successfully',
    'DOCUMENTS_SENT': 'Documents sent to SISGEN successfully',
    'XML_GENERATED': 'XML generated successfully',
}

# Logging Configuration
LOGGING_CONFIG = {
    'SISGEN_SERVICE': 'sisgen_service',
    'DOCUMENT_SEARCH': 'document_search',
    'XML_GENERATOR': 'xml_generator',
    'SOAP_CLIENT': 'soap_client',
    'DATA_PROCESSOR': 'data_processor',
}