"""
This module contains the data processor service for SISGEN integration.
Handles temporary tables and data processing for SISGEN XML generation.
"""

from typing import Dict, List, Optional
import logging
from datetime import datetime
from django.db import connection
from django.conf import settings

logger = logging.getLogger(__name__)

class DataProcessorService:
    def __init__(self):
        self.logger = logger
    
    def process_temp_tables(self, kardex_list: List[str]) -> Dict:
        """
        Process temporary tables for SISGEN XML generation
        Returns: {
            'documents': [...],  # Document data for XML
            'errores': [...],    # Error list
            'observaciones': [...], # Observations
            'personas': [...]    # Person errors
        }
        """
        try:
            # Clear temp tables
            self._clear_temp_tables()
            
            # Insert into sisgen_temp
            self._insert_sisgen_temp(kardex_list)
            
            # Process legal entities
            juridicas = self._process_juridicas()
            
            # Process natural persons
            naturales = self._process_naturales()
            
            # Process interventions
            intervenciones = self._process_intervenciones()
            
            # Get document data for XML generation
            documents = self._get_documents_for_xml()
            
            return {
                'documents': documents,
                'juridicas_count': len(juridicas),
                'naturales_count': len(naturales),
                'intervenciones_count': len(intervenciones),
                'errores': [],  # Will be populated during XML generation
                'observaciones': [],
                'personas': []
            }
            
        except Exception as e:
            self.logger.error(f"Error processing temp tables: {str(e)}")
            raise
    
    def _clear_temp_tables(self):
        """Clear all temporary tables"""
        tables = [
            'sisgen_temp',
            'sisgen_temp_j',
            'sisgen_temp_n',
            'sisgen_intervenciones_6',
            'sisgen_mensaje'  # Added for message storage
        ]
        
        with connection.cursor() as cursor:
            for table in tables:
                cursor.execute(f"TRUNCATE {table}")
    
    def _insert_sisgen_temp(self, kardex_list: List[str]):
        """Insert data into sisgen_temp table"""
        if not kardex_list:
            return
            
        placeholders = ', '.join(['%s'] * len(kardex_list))
        query = f"""
            INSERT INTO sisgen_temp (
                idkardex, kardex, idtipkar, fecha_ingreso,
                codactos, contrato, folioini, foliofin,
                fecha_conclusion, numescritura, fechaescritura, cod_ancert
            )
            SELECT 
                k.idkardex, k.kardex, k.idtipkar, k.fechaingreso,
                k.codactos, k.contrato, k.folioini, k.foliofin,
                k.fechaconclusion, k.numescritura, k.fechaescritura,
                IF(ta.cod_ancert IS NULL, '', ta.cod_ancert)
            FROM kardex k
            LEFT JOIN tiposdeacto ta ON SUBSTRING(k.codactos,1,3) = ta.idtipoacto
            WHERE k.kardex IN ({placeholders})
        """
        
        with connection.cursor() as cursor:
            cursor.execute(query, kardex_list)
    
    def update_document_statuses(self, sisgen_response: Dict):
        """Update document statuses based on SISGEN response"""
        current_date = datetime.now().strftime('%d/%m/%Y')
        current_time = datetime.now().strftime('%H:%M:%S')
        
        for doc in sisgen_response.get('DocumentoNotarial', []):
            kardex = doc['Documento']['NumKardex']
            status = doc['Status']
            
            # Map status to estado_sisgen
            estado_map = {
                'FALLIDO': 3,
                'GUARDADO': 1,
                'CON OBSERVACIONES': 2
            }
            estado = estado_map.get(status, 0)
            
            # Insert into sisgen table
            self._insert_sisgen_status(
                kardex=kardex,
                tipo_kardex=doc['Documento']['TipoInstrumento'],
                num_escritura=doc['Documento']['NumDocumento'],
                fecha_instrumento=doc['Documento']['FechaInstrumento'],
                fecha_envio=current_date,
                hora_envio=current_time,
                status=status,
                estado=estado
            )
            
            # Update kardex table
            self._update_kardex_status(kardex, estado)
            
            # Process errors if any
            if 'ERRORS' in doc['Documento']:
                self._process_document_errors(kardex, doc['Documento']['ERRORS'])
            
            if 'Maestros' in doc and 'ERRORS' in doc['Maestros']:
                self._process_maestros_errors(kardex, doc['Maestros']['ERRORS'])
            
            if 'Operaciones' in doc:
                self._process_operaciones_errors(kardex, doc['Operaciones'])
    
    def get_final_status(self) -> Dict:
        """Get final status counts and messages"""
        query = """
            SELECT DISTINCT
                sm.mensaje,
                s.tipo_kardex AS TIPKAR,
                s.kardex AS kardex,
                s.num_escritura AS NUM_ESC,
                s.fech_envio AS FEC_ENVIO,
                s.hora_envio AS HORA_ENVIO,
                s.estado AS estado,
                IFNULL(sm.mensaje, '') AS mensaje,
                s.status AS status,
                st.idkardex AS IDKARDEX,
                st.contrato AS contrato
            FROM sisgen s
            LEFT JOIN sisgen_mensaje sm ON s.kardex = sm.kardex
            INNER JOIN sisgen_temp st ON s.kardex = st.kardex
            ORDER BY s.kardex ASC
        """
        
        with connection.cursor() as cursor:
            cursor.execute(query)
            columns = [col[0] for col in cursor.description]
            data = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            # Get status counts
            cursor.execute("SELECT COUNT(*) FROM sisgen WHERE status = 'GUARDADO'")
            guardados = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM sisgen WHERE status = 'FALLIDO'")
            fallidos = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM sisgen WHERE status = 'CON OBSERVACIONES'")
            observados = cursor.fetchone()[0]
            
            return {
                'data': data,
                'guardados': guardados,
                'fallidos': fallidos,
                'observados': observados
            }
    
    def _get_documents_for_xml(self) -> List[Dict]:
        """Get document data for XML generation"""
        query = """
            SELECT 
                k.*, 
                cn.codnotario, cn.codoficial, cn.coduif,
                CONCAT(cn.nombre, ' ', cn.apellido) as nombre_notario,
                cn.direccion as direccion_notario,
                cn.distrito as distrito_notario,
                cn.provincia as provincia_notario,
                cn.departamento as departamento_notario
            FROM sisgen_temp k
            LEFT JOIN confinotario cn ON 1=1
            WHERE cn.codnotario IS NOT NULL
        """
        
        with connection.cursor() as cursor:
            cursor.execute(query)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def _insert_sisgen_status(self, **kwargs):
        """Insert status into sisgen table"""
        fields = ', '.join(kwargs.keys())
        placeholders = ', '.join(['%s'] * len(kwargs))
        query = f"INSERT INTO sisgen ({fields}) VALUES ({placeholders})"
        
        with connection.cursor() as cursor:
            cursor.execute(query, list(kwargs.values()))
            
            # Also insert into sisgen_report for history
            cursor.execute(f"INSERT INTO sisgen_report ({fields}) VALUES ({placeholders})", 
                         list(kwargs.values()))
    
    def _update_kardex_status(self, kardex: str, estado: int):
        """Update kardex estado_sisgen"""
        query = "UPDATE kardex SET estado_sisgen = %s WHERE kardex = %s"
        with connection.cursor() as cursor:
            cursor.execute(query, [estado, kardex])
    
    def _process_document_errors(self, kardex: str, errors: List[str]):
        """Process document level errors"""
        self._insert_error_messages(kardex, errors)
    
    def _process_maestros_errors(self, kardex: str, errors: List[str]):
        """Process maestros level errors"""
        self._insert_error_messages(kardex, errors)
    
    def _process_operaciones_errors(self, kardex: str, operaciones: Dict):
        """Process operaciones level errors"""
        for operacion in operaciones.get('Operacion', []):
            if 'ERRORS' in operacion:
                self._insert_error_messages(kardex, operacion['ERRORS'])
            
            if 'Operantes' in operacion and 'ERRORS' in operacion['Operantes']:
                self._insert_error_messages(kardex, operacion['Operantes']['ERRORS'])
            
            if 'MediosPagos' in operacion:
                for pago in operacion['MediosPagos'].get('MedioPago', []):
                    if 'ERRORS' in pago:
                        self._insert_error_messages(kardex, pago['ERRORS'])
    
    def _insert_error_messages(self, kardex: str, messages: List[str]):
        """Insert error messages into sisgen_mensaje table"""
        query = "INSERT INTO sisgen_mensaje (kardex, mensaje) VALUES (%s, %s)"
        with connection.cursor() as cursor:
            for msg in messages:
                cursor.execute(query, [kardex, msg])