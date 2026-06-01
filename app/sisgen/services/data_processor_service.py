"""
This module contains the data processor service for SISGEN integration.
"""

from typing import Dict, List, Optional
from datetime import datetime
from django.db import connection
import logging
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

class DataProcessorService:
    def __init__(self):
        self.logger = logger

    def process_documents_batch(self, documents: List[Dict[str, str]]) -> Dict:
        """
        Process multiple documents for SISGEN in a single batch.
        Args:
            documents: List of {'kardex': str, 'idkardex': str}
        """
        try:
            # Clear previous data
            self._clear_temp_tables()
            
            # Process each document and collect data
            processed_docs = []
            for doc in documents:
                # Get document data
                doc_data = self._get_document_data(doc['kardex'], doc['idkardex'])
                if not doc_data:
                    self.logger.warning(f"Document not found: {doc['kardex']}")
                    continue
                
                # Get notary data (same for all docs)
                if not processed_docs:  # Only get once
                    notary_data = self._get_notary_data()
                    if not notary_data:
                        raise Exception("Notary data not found")
                
                # Get participants data
                participants = self._get_participants_data(doc['kardex'])
                
                # Add to processed docs
                processed_docs.append({
                    **doc_data,
                    'notary_data': notary_data,
                    'participants': participants
                })
            
            # Return combined result
            return {
                'documents': processed_docs,
                'errores': [],
                'observaciones': [],
                'personas': []
            }
            
        except Exception as e:
            self.logger.error(f"Error processing document batch: {str(e)}")
            raise
        
    def process_document(self, kardex: str, idkardex: str) -> Dict:
        """
        Process a single document for SISGEN.
        Similar to PHP's kardexml() function.
        """
        try:
            # Clear previous data
            self._clear_temp_tables()
            
            # Get document data
            doc_data = self._get_document_data(kardex, idkardex)
            if not doc_data:
                raise Exception(f"Document not found: {kardex}")
            
            # Get notary data
            notary_data = self._get_notary_data()
            if not notary_data:
                raise Exception("Notary data not found")
            
            # Get participants data
            participants = self._get_participants_data(kardex)
            
            # Combine all data
            result = {
                'documents': [{
                    **doc_data,
                    'notary_data': notary_data,
                    'participants': participants
                }],
                'errores': [],
                'observaciones': [],
                'personas': []
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error processing document: {str(e)}")
            raise
    
    def _clear_temp_tables(self):
        """Clear temporary tables"""
        tables = ['sisgen_temp', 'sisgen_mensaje', 'sisgen']
        
        with connection.cursor() as cursor:
            for table in tables:
                cursor.execute(f"TRUNCATE {table}")
    
    def _get_document_data(self, kardex: str, idkardex: str) -> Optional[Dict]:
        """Get document data from kardex table"""
        query = """
            SELECT k.*, 
                   IF(ta.cod_ancert IS NULL,'',ta.cod_ancert) AS cod_ancert,
                   ta.actouif, ta.actosunat,
                   ta.mediospago, ta.cuantia, ta.origenfondo, ta.impuestorenta,
                   IFNULL(ta.desacto, '') AS desacto
            FROM kardex k
            LEFT JOIN tiposdeacto ta ON SUBSTRING(k.codactos,1,3) = ta.idtipoacto
            WHERE k.kardex = %s AND k.idkardex = %s
        """
        
        with connection.cursor() as cursor:
            cursor.execute(query, [kardex, idkardex])
            columns = [col[0] for col in cursor.description]
            row = cursor.fetchone()
            
            if not row:
                return None
                
            return dict(zip(columns, row))
    
    def _get_notary_data(self) -> Optional[Dict]:
        """Get notary data from confinotario table"""
        query = """
            SELECT codnotario, codoficial, coduif,
                   CONCAT(nombre, ' ', apellido) as nombre_notario,
                   direccion, distrito, provincia, departamento
            FROM confinotario
            LIMIT 1
        """
        
        with connection.cursor() as cursor:
            cursor.execute(query)
            columns = [col[0] for col in cursor.description]
            row = cursor.fetchone()
            
            if not row:
                return None
                
            return dict(zip(columns, row))
    
    def _get_participants_data(self, kardex: str) -> List[Dict]:
        """Get participants data"""
        query = """
            SELECT cx.*, cl.*, co.*
            FROM contratantesxacto cx
            LEFT JOIN cliente2 cl ON cx.idcontratante = cl.idcontratante
            LEFT JOIN contratantes co ON cl.idcontratante = co.idcontratante
            WHERE cx.kardex = %s
        """
        
        with connection.cursor() as cursor:
            cursor.execute(query, [kardex])
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def update_document_statuses(self, response_text: str):
        """Update document statuses based on SISGEN response"""
        try:
            # Parse XML response
            root = ET.fromstring(response_text)
            
            # Define namespaces
            namespaces = {
                'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
                'ns2': 'http://cnlws.notarios.org.pe/',
                'ns3': 'http://sisgen.notarios.org.pe/SISGEN/XML'
            }
            
            # Get current date/time
            current_date = datetime.now().strftime('%d/%m/%Y')
            current_time = datetime.now().strftime('%H:%M:%S')
            
            # Find return element and get status/message
            return_elem = root.find('.//ns2:setDocumentosNotarialesResponse/return', namespaces)
            if return_elem is None:
                self.logger.error("Could not find return element in response")
                return
                
            status = return_elem.find('status').text if return_elem.find('status') is not None else None
            message = return_elem.find('message').text if return_elem.find('message') is not None else ''
            
            # Find DocumentoNotarial elements
            doc_notariales = root.findall('.//ns3:DocumentoNotarial', namespaces)
            
            for doc in doc_notariales:
                # Get Status and Documento elements
                status_elem = doc.find('.//ns3:Status', namespaces)
                documento = doc.find('.//ns3:Documento', namespaces)
                
                if status_elem is not None and documento is not None:
                    doc_status = status_elem.text
                    kardex = documento.find('.//ns3:NumKardex', namespaces).text if documento.find('.//ns3:NumKardex', namespaces) is not None else ''
                    
                    # Map status to estado_sisgen
                    estado_map = {
                        'FALLIDO': 3,
                        'GUARDADO': 1,
                        'CON OBSERVACIONES': 2
                    }
                    estado = estado_map.get(doc_status, 0)
                    
                    # Get document details
                    tipo_instrumento = documento.find('.//ns3:TipoInstrumento', namespaces)
                    tipo_instrumento = tipo_instrumento.text if tipo_instrumento is not None else ''
                    
                    num_escritura = documento.find('.//ns3:NumDocumento', namespaces)
                    num_escritura = num_escritura.text if num_escritura is not None else ''
                    
                    fecha_instrumento = documento.find('.//ns3:FechaInstrumento', namespaces)
                    fecha_instrumento = fecha_instrumento.text if fecha_instrumento is not None else ''
                    
                    # Insert into sisgen and sisgen_report tables
                    self._insert_sisgen_status(
                        tipo_kardex=tipo_instrumento,
                        kardex=kardex,
                        num_escritura=num_escritura,
                        fecha_instrumento=fecha_instrumento,
                        fech_envio=current_date,
                        hora_envio=current_time,
                        status=doc_status,
                        estado=estado
                    )
                    
                    # Update kardex status
                    self._update_kardex_status(kardex, estado)
                    
                    # Process errors if any
                    errors_elem = doc.find('.//ns3:ERRORS', namespaces)
                    if errors_elem is not None:
                        error_messages = []
                        for error in errors_elem.findall('.//ns3:ERROR', namespaces):
                            if error.text:
                                error_messages.append(error.text)
                        if error_messages:
                            self._process_errors(kardex, error_messages)
                    
                    self.logger.info(f"Updated status for kardex {kardex}: {doc_status} (estado: {estado})")
                    
        except Exception as e:
            self.logger.error(f"Error updating document statuses: {str(e)}")
            raise
    
    def _insert_sisgen_status(self, **kwargs):
        """Insert status into sisgen tables"""
        fields = ', '.join(kwargs.keys())
        placeholders = ', '.join(['%s'] * len(kwargs))
        
        for table in ['sisgen', 'sisgen_report']:
            query = f"INSERT INTO {table} ({fields}) VALUES ({placeholders})"
            with connection.cursor() as cursor:
                cursor.execute(query, list(kwargs.values()))
    
    def _update_kardex_status(self, kardex: str, estado: int):
        """Update kardex estado_sisgen"""
        query = "UPDATE kardex SET estado_sisgen = %s WHERE kardex = %s"
        with connection.cursor() as cursor:
            cursor.execute(query, [estado, kardex])
    
    def _process_errors(self, kardex: str, errors: List[str]):
        """Insert error messages into sisgen_mensaje table"""
        query = "INSERT INTO sisgen_mensaje (kardex, mensaje) VALUES (%s, %s)"
        with connection.cursor() as cursor:
            for msg in errors:
                cursor.execute(query, [kardex, msg])
    
    def get_final_status(self) -> Dict:
        """Get final status and messages"""
        query = """
            SELECT DISTINCT
                sm.mensaje,
                s.tipo_kardex AS TIPKAR,
                s.kardex,
                s.num_escritura AS NUM_ESC,
                s.fech_envio AS FEC_ENVIO,
                s.hora_envio AS HORA_ENVIO,
                s.estado,
                IFNULL(sm.mensaje, '') AS mensaje,
                s.status,
                st.idkardex AS IDKARDEX,
                st.contrato
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
            guardados = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT COUNT(*) FROM sisgen WHERE status = 'FALLIDO'")
            fallidos = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT COUNT(*) FROM sisgen WHERE status = 'CON OBSERVACIONES'")
            observados = cursor.fetchone()[0] or 0
            
            return {
                'data': data,
                'guardados': guardados,
                'fallidos': fallidos,
                'observados': observados
            }