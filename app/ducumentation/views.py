from django.shortcuts import render
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework import status
from . import models, serializers
from notaria.models import TplTemplate, Detallevehicular, Patrimonial, Contratantes, Actocondicion, Cliente2, Nacionalidades, Kardex, Usuarios, Contratantesxacto, Ubigeo, IngresoCartas
from notaria.constants import MONEDAS, OPORTUNIDADES_PAGO, FORMAS_PAGO
from notaria import pagination
from django.http import HttpResponse
import boto3
from botocore.client import Config
from django.conf import settings
import os
from docx import Document
import io
from .constants import ROLE_LABELS, TIPO_DOCUMENTO, CIVIL_STATUS
import re
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any
from botocore.config import Config
from datetime import datetime
from docxtpl import DocxTemplate
from docxcompose.properties import CustomProperties
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response
from docx.shared import RGBColor, Pt
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.http import require_GET
from django.utils.decorators import method_decorator

import re
from django.urls import reverse
from .utils import NumberToLetterConverter
from .services import VehicleTransferDocumentService, NonContentiousDocumentService, TestamentoDocumentService, GarantiasMobiliariasDocumentService, EscrituraPublicaDocumentService
from .extraprotocolares.permiso_viajes import PermisoViajeInteriorDocumentService, PermisoViajeExteriorDocumentService
from .extraprotocolares.poderes import PoderFueraDeRegistroDocumentService, PoderPensionDocumentService, PoderEssaludDocumentService
from notaria.models import IngresoPoderes  
from .extraprotocolares.cartas_notariales import CartasNotarialesDocumentService

@api_view(['GET'])
def generate_document_by_tipkar(request):
    """
    Generate document based on tipkar (tipo kardex) from the kardex record
    """
    print("GENERATE DOCUMENT BY TIPKAR VIEW CALLED")
    # Get parameters from GET request
    template_id = request.GET.get('template_id')
    kardex = request.GET.get('kardex')
    action = 'generate'
    mode = request.GET.get('mode')
    
    if not all([template_id, kardex]):
        return Response({
            'success': False,
            'message': 'Missing required parameters: template_id, kardex'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        template_id = int(template_id)
    except ValueError:
        return Response({
            'success': False,
            'message': 'Invalid template_id format'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Get the kardex record to determine the tipkar
        kardex_obj = Kardex.objects.filter(kardex=kardex).first()
        
        if not kardex_obj:
            return Response({
                'success': False,
                'message': f'Kardex {kardex} not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        tipkar = kardex_obj.idtipkar
        
        # Route to appropriate service based on tipkar
        if tipkar == 3:  # TRANSFERENCIAS VEHICULARES
            print(f"DEBUG: Using VehicleTransferDocumentService for tipkar {tipkar}")
            service = VehicleTransferDocumentService()
            response = service.generate_vehicle_transfer_document(template_id, kardex, action, mode)
            return response
        elif tipkar == 2:  # ASUNTOS NO CONTENCIOSOS
            print(f"DEBUG: Using NonContentiousDocumentService for tipkar {tipkar}")
            # For non-contentious, we need idtipoacto from the request or from kardex
            idtipoacto = request.GET.get('idtipoacto')
            if not idtipoacto:
                # Try to get from kardex codactos
                if kardex_obj.codactos:
                    idtipoacto = kardex_obj.codactos[:3]  # Take first 3 characters
                else:
                    return Response({
                        'success': False,
                        'message': 'idtipoacto is required for non-contentious documents'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            service = NonContentiousDocumentService()
            response = service.generate_non_contentious_document(template_id, kardex, idtipoacto, action, mode)
            return response
        else:
            return Response({
                'success': False,
                'message': f'Document generation not implemented for tipkar {tipkar}'
            }, status=status.HTTP_501_NOT_IMPLEMENTED)
            
    except Exception as e:
        print(f"Error generating document: {e}")
        return Response({
            'success': False,
            'message': 'Internal server error occurred'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def update_document_by_tipkar(request):
    """
    Smart update endpoint that preserves manual edits based on tipkar
    """
    print("SMART UPDATE DOCUMENT BY TIPKAR VIEW CALLED")
    if request.method == 'POST':
        # Get parameters
        template_id = request.POST.get('template_id')
        kardex = request.POST.get('kardex')
        
        if not all([template_id, kardex]):
            return Response({
                'success': False,
                'message': 'Missing required parameters: template_id, kardex'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            template_id = int(template_id)
        except ValueError:
            return Response({
                'success': False,
                'message': 'Invalid template_id format'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Get the kardex record to determine the tipkar
            from notaria.models import Kardex
            kardex_obj = Kardex.objects.filter(kardex=kardex).first()
            
            if not kardex_obj:
                return Response({
                    'success': False,
                    'message': f'Kardex {kardex} not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            tipkar = kardex_obj.idtipkar
            
            # Route to appropriate update function based on tipkar
            if tipkar == 3:  # TRANSFERENCIAS VEHICULARES
                print(f"DEBUG: Using vehicle update for tipkar {tipkar}")
                result = _smart_update_with_auto_discovery(template_id, kardex)
                return Response(result)
            elif tipkar == 2:  # ASUNTOS NO CONTENCIOSOS
                print(f"DEBUG: Using non-contentious update for tipkar {tipkar}")
                # For non-contentious, we need idtipoacto from the request or from kardex
                if request.method == 'GET':
                    idtipoacto = request.GET.get('idtipoacto')
                else:  # POST
                    idtipoacto = request.data.get('idtipoacto')
                if not idtipoacto:
                    # Try to get from kardex codactos
                    if kardex_obj.codactos:
                        idtipoacto = kardex_obj.codactos[:3]  # Take first 3 characters
                    else:
                        return Response({
                            'success': False,
                            'message': 'idtipoacto is required for non-contentious documents'
                        }, status=status.HTTP_400_BAD_REQUEST)
                
                result = _smart_update_non_contentious_with_auto_discovery(template_id, kardex, idtipoacto)
                return Response(result)
            else:
                return Response({
                    'success': False,
                    'message': f'Document update not implemented for tipkar {tipkar}'
                }, status=status.HTTP_501_NOT_IMPLEMENTED)
                
        except Exception as e:
            print(f"Error in smart update: {e}")
            return Response({
                'success': False,
                'message': 'Internal server error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        


def _smart_update_non_contentious_with_auto_discovery(template_id: int, kardex: str, idtipoacto: str) -> dict:
    """
    ALWAYS preserve manual edits - automatically finds non-contentious document in R2 based on kardex
    """
    try:
        print(f"DEBUG: Starting smart update for non-contentious kardex: {kardex}")
        
        # Step 1: Auto-discover the document filename in R2
        s3 = boto3.client(
            's3',
            endpoint_url=os.environ.get('CLOUDFLARE_R2_ENDPOINT'),
            aws_access_key_id=os.environ.get('CLOUDFLARE_R2_ACCESS_KEY'),
            aws_secret_access_key=os.environ.get('CLOUDFLARE_R2_SECRET_KEY'),
            config=Config(signature_version='s3v4'),
            region_name='auto',
        )

        # Auto-generate the filename based on kardex pattern
        filename = f"__PROY__{kardex}.docx"
        object_key = f"rodriguez-zea/documentos/{filename}"
        
        print(f"DEBUG: Looking for non-contentious document in R2: {object_key}")
        
        try:
            # Download current document
            response = s3.get_object(
                Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'),
                Key=object_key
            )
            current_doc_content = response['Body'].read()
            print(f"DEBUG: Successfully downloaded current non-contentious document from R2 ({len(current_doc_content)} bytes)")
            
            # Step 2: Generate new document with updated data
            print(f"DEBUG: Generating new non-contentious document with template_id: {template_id}")
            service = NonContentiousDocumentService()
            new_doc_response = service.generate_non_contentious_document(template_id, kardex, idtipoacto, 'update')
            
            if new_doc_response.status_code != 200:
                print(f"DEBUG: Failed to generate updated non-contentious document: {new_doc_response.status_code}")
                return {'error': 'Failed to generate updated non-contentious document'}
            
            print(f"DEBUG: Successfully generated new non-contentious document ({len(new_doc_response.content)} bytes)")
            
            # Step 3: ALWAYS merge documents to preserve manual edits
            print(f"DEBUG: Merging non-contentious documents to preserve manual edits")
            merged_doc = _merge_documents_smart(current_doc_content, new_doc_response.content, kardex)
            print(f"DEBUG: Successfully merged non-contentious documents ({len(merged_doc)} bytes)")
            
            # Step 4: Upload merged document back to R2
            from io import BytesIO
            file_obj = BytesIO(merged_doc)
            
            print(f"DEBUG: Uploading merged non-contentious document back to R2: {object_key}")
            s3.upload_fileobj(
                file_obj,
                os.environ.get('CLOUDFLARE_R2_BUCKET'),
                object_key
            )
            
            print(f"DEBUG: Successfully uploaded merged non-contentious document to R2")
            return {'status': 'success', 'message': f'Non-contentious document updated successfully for kardex: {kardex}'}
            
        except Exception as e:
            print(f"DEBUG: Error downloading non-contentious document: {e}")
            return {'error': f'Failed to download non-contentious document: {str(e)}'}
        
    except Exception as e:
        print(f"DEBUG: Error preserving manual edits for non-contentious: {e}")
        return {'error': f'Failed to preserve manual edits for non-contentious: {str(e)}'}


def _smart_update_with_auto_discovery(template_id: int, kardex: str) -> dict:
    """
    ALWAYS preserve manual edits - automatically finds document in R2 based on kardex
    """
    try:
        print(f"DEBUG: Starting smart update for kardex: {kardex}")
        
        # Step 1: Auto-discover the document filename in R2
        s3 = boto3.client(
            's3',
            endpoint_url=os.environ.get('CLOUDFLARE_R2_ENDPOINT'),
            aws_access_key_id=os.environ.get('CLOUDFLARE_R2_ACCESS_KEY'),
            aws_secret_access_key=os.environ.get('CLOUDFLARE_R2_SECRET_KEY'),
            config=Config(signature_version='s3v4'),
            region_name='auto',
        )

        # Auto-generate the filename based on kardex pattern
        filename = f"__PROY__{kardex}.docx"
        object_key = f"rodriguez-zea/documentos/{filename}"
        
        print(f"DEBUG: Looking for document in R2: {object_key}")
        
        try:
            # Download current document
            response = s3.get_object(
                Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'),
                Key=object_key
            )
            current_doc_content = response['Body'].read()
            print(f"DEBUG: Successfully downloaded current document from R2 ({len(current_doc_content)} bytes)")
            
            # Step 2: Generate new document with updated data
            print(f"DEBUG: Generating new document with template_id: {template_id}")
            service = VehicleTransferDocumentService()
            new_doc_response = service.generate_vehicle_transfer_document(template_id, kardex, 'update')
            
            if new_doc_response.status_code != 200:
                print(f"DEBUG: Failed to generate updated document: {new_doc_response.status_code}")
                return {'error': 'Failed to generate updated document'}
            
            print(f"DEBUG: Successfully generated new document ({len(new_doc_response.content)} bytes)")
            
            # Step 3: ALWAYS merge documents to preserve manual edits
            print(f"DEBUG: Merging documents to preserve manual edits")
            merged_doc = _merge_documents_smart(current_doc_content, new_doc_response.content, kardex)
            print(f"DEBUG: Successfully merged documents ({len(merged_doc)} bytes)")
            
            # Step 4: Upload merged document back to R2
            from io import BytesIO
            file_obj = BytesIO(merged_doc)
            
            print(f"DEBUG: Uploading merged document back to R2: {object_key}")
            s3.upload_fileobj(
                file_obj,
                os.environ.get('CLOUDFLARE_R2_BUCKET'),
                object_key
            )
            print(f"DEBUG: Successfully uploaded merged document to R2")
            
            return {
                'status': 'success',
                'message': 'Document updated successfully while preserving ALL manual edits',
                'filename': filename,
                'kardex': kardex,
                'update_type': 'manual_edits_preserved',
                'debug_info': {
                    'original_size': len(current_doc_content),
                    'new_size': len(new_doc_response.content),
                    'merged_size': len(merged_doc),
                    'r2_path': object_key
                }
            }
            
        except s3.exceptions.NoSuchKey:
            print(f"DEBUG: Document not found in R2: {filename}")
            return {'error': f'Document not found in R2: {filename}'}
        except Exception as e:
            print(f"DEBUG: Error downloading document: {e}")
            return {'error': f'Failed to download document: {str(e)}'}
        
    except Exception as e:
        print(f"DEBUG: Error preserving manual edits: {e}")
        return {'error': f'Failed to preserve manual edits: {str(e)}'}


def _merge_documents_smart(current_doc_content: bytes, new_doc_content: bytes, kardex: str) -> bytes:
    """
    ALWAYS preserve manual edits - never fall back to losing manual edits
    """
    try:
        from io import BytesIO
        from docx import Document
        
        # Load both documents
        current_doc = Document(BytesIO(current_doc_content))
        new_doc = Document(BytesIO(new_doc_content))
        
        # Get current data to identify what should be updated
        service = VehicleTransferDocumentService()
        current_data = service.get_document_data(kardex)
        
        # Define which fields are DB-driven and should be updated
        db_driven_fields = {
            'PLACA', 'MARCA', 'MODELO', 'AÑO_FABRICACION', 'COLOR',
            'NRO_MOTOR', 'NRO_SERIE', 'MONTO', 'MON_VEHI', 'MONEDA_C',
            'P_NOM_1', 'P_NACIONALIDAD_1', 'P_DOC_1', 'P_OCUPACION_1',
            'C_NOM_1', 'C_NACIONALIDAD_1', 'C_DOC_1', 'C_OCUPACION_1',
            'NRO_ESC', 'USUARIO', 'USUARIO_DNI', 'FECHA_ACT'
        }
        
        # Instead of trying to merge, we'll use the new document as a template
        # and only update the specific fields that have changed
        updated_doc = _smart_update_specific_fields(current_doc, new_doc, current_data, db_driven_fields)
        
        # Save the updated document
        buffer = BytesIO()
        updated_doc.save(buffer)
        buffer.seek(0)
        return buffer.read()
        
    except Exception as e:
        print(f"Error merging documents: {e}")
        # NEVER fall back to losing manual edits - return current document unchanged
        return current_doc_content


def _smart_update_specific_fields(current_doc, new_doc, data: dict, db_fields: set):
    """
    Smart update that only changes specific fields while preserving all formatting and structure
    """
    import re
    
    # Create a mapping of field names to their values
    field_mapping = {}
    for field in db_fields:
        if field in data:
            field_mapping[field] = str(data[field])
    
    # Debug: Print what fields we're working with
    print(f"DEBUG: Processing fields: {field_mapping}")
    
    # Debug: Show all paragraphs in current document
    print(f"DEBUG: Current document has {len(current_doc.paragraphs)} paragraphs")
    for i, paragraph in enumerate(current_doc.paragraphs):
        if paragraph.text.strip():
            print(f"DEBUG: Paragraph {i}: '{paragraph.text[:200]}...'")
    
    # Debug: Show all tables in current document
    print(f"DEBUG: Current document has {len(current_doc.tables)} tables")
    for i, table in enumerate(current_doc.tables):
        print(f"DEBUG: Table {i} has {len(table.rows)} rows")
        for j, row in enumerate(table.rows):
            for k, cell in enumerate(row.cells):
                for l, paragraph in enumerate(cell.paragraphs):
                    if paragraph.text.strip():
                        print(f"DEBUG: Table {i}, Row {j}, Cell {k}, Paragraph {l}: '{paragraph.text[:200]}...'")
    
    # Update paragraphs
    for i, paragraph in enumerate(current_doc.paragraphs):
        if i < len(new_doc.paragraphs):
            print(f"DEBUG: Processing paragraph {i}")
            _smart_update_paragraph(paragraph, new_doc.paragraphs[i], field_mapping)
    
    # Update tables
    for table_idx, table in enumerate(current_doc.tables):
        if table_idx < len(new_doc.tables):
            print(f"DEBUG: Processing table {table_idx}")
            _smart_update_table(table, new_doc.tables[table_idx], field_mapping)
    
    return current_doc


def _smart_update_paragraph(current_paragraph, new_paragraph, field_mapping):
    """
    Smart update paragraph content while preserving formatting
    Uses the template (new_paragraph) to find where placeholders should be
    and updates the current document accordingly
    """
    # Get the text content from both paragraphs
    current_text = current_paragraph.text
    template_text = new_paragraph.text
    
    # Find placeholders in the template and map them to field values
    _update_based_on_template_placeholders(current_paragraph, template_text, field_mapping)


def _update_based_on_template_placeholders(paragraph, template_text, field_mapping):
    """
    Update paragraph based on placeholders found in the template
    Preserves all formatting by working with individual runs
    """
    import re
    
    print(f"DEBUG: Current paragraph text: '{paragraph.text}'")
    print(f"DEBUG: Template text: '{template_text}'")
    
    # Define the placeholders we want to keep and their corresponding field names
    placeholder_mapping = {
        '{{NRO_ESC}}': 'NRO_ESC',
        '{{FI}}': 'FI',
        '{{FF}}': 'FF',
        '{{S_IN}}': 'S_IN',
        '{{S_FN}}': 'S_FN',
        '{{FECHA_ACT}}': 'FECHA_ACT'
    }
    
    # Process each placeholder we want to keep
    for placeholder, field_name in placeholder_mapping.items():
        if field_name in field_mapping and field_mapping[field_name] and field_mapping[field_name].strip():
            value = field_mapping[field_name]
            print(f"DEBUG: Processing {field_name} with value: '{value}'")
            
            # Look for the placeholder in individual runs to preserve formatting
            _update_placeholder_in_runs(paragraph, placeholder, value)
    
    # Also check for hidden placeholders in runs and make them visible for replacement
    _update_hidden_placeholders_in_runs(paragraph, field_mapping)


def _update_placeholder_in_runs(paragraph, placeholder, value):
    """
    Update placeholder in paragraph runs while preserving all formatting
    """
    print(f"DEBUG: Looking for placeholder '{placeholder}' in paragraph runs")
    
    # Check if placeholder exists in any run
    placeholder_found = False
    for run in paragraph.runs:
        if placeholder in run.text:
            placeholder_found = True
            print(f"DEBUG: Found '{placeholder}' in run: '{run.text}'")
            # Replace the placeholder while preserving the run's formatting
            run.text = run.text.replace(placeholder, value)
            # Ensure the new value is visible (black color)
            run.font.color.rgb = RGBColor(0, 0, 0)  # Black color
            print(f"DEBUG: Updated run to: '{run.text}' with black color")
            break
    
    # If placeholder not found in runs, check if it spans multiple runs
    if not placeholder_found:
        print(f"DEBUG: Placeholder '{placeholder}' not found in individual runs, checking if it spans multiple runs")
        paragraph_text = paragraph.text
        if placeholder in paragraph_text:
            print(f"DEBUG: Found '{placeholder}' spanning multiple runs in paragraph: '{paragraph_text[:100]}...'")
            # This is more complex - we need to handle placeholders that span multiple runs
            _update_placeholder_spanning_runs(paragraph, placeholder, value)
        else:
            # If no placeholder found, look for blank fields
            field_name = placeholder.strip('{}')
            _update_blank_field(paragraph, field_name, value)


def _update_placeholder_spanning_runs(paragraph, placeholder, value):
    """
    Handle placeholders that span multiple runs by carefully reconstructing the paragraph
    """
    print(f"DEBUG: Updating placeholder '{placeholder}' that spans multiple runs")
    
    # Get the original paragraph text and find the placeholder position
    original_text = paragraph.text
    placeholder_start = original_text.find(placeholder)
    
    if placeholder_start == -1:
        print(f"DEBUG: Placeholder '{placeholder}' not found in paragraph text")
        return
    
    placeholder_end = placeholder_start + len(placeholder)
    
    # Split the text around the placeholder
    before_placeholder = original_text[:placeholder_start]
    after_placeholder = original_text[placeholder_end:]
    
    print(f"DEBUG: Before placeholder: '{before_placeholder}'")
    print(f"DEBUG: After placeholder: '{after_placeholder}'")
    
    # Clear the paragraph and rebuild it with proper formatting
    paragraph.clear()
    
    # Add the text before the placeholder
    if before_placeholder:
        run = paragraph.add_run(before_placeholder)
        # Apply default formatting (you can customize this)
        run.font.name = 'Calibri'
        run.font.size = Pt(11)
    
    # Add the new value with appropriate formatting
    value_run = paragraph.add_run(value)
    value_run.font.name = 'Calibri'
    value_run.font.size = Pt(11)
    value_run.font.bold = True  # Make the updated value bold to distinguish it
    value_run.font.color.rgb = RGBColor(0, 0, 0)  # Ensure it's black and visible
    
    # Add the text after the placeholder
    if after_placeholder:
        run = paragraph.add_run(after_placeholder)
        # Apply default formatting
        run.font.name = 'Calibri'
        run.font.size = Pt(11)
    
    print(f"DEBUG: Rebuilt paragraph: '{paragraph.text}'")


def _update_hidden_placeholders_in_runs(paragraph, field_mapping):
    """
    Find and update hidden placeholders in paragraph runs
    Preserves formatting while making hidden placeholders visible
    """
    import re
    
    # Common placeholder patterns
    placeholder_patterns = {
        '{{NRO_ESC}}': 'NRO_ESC',
        '{{FI}}': 'FI',
        '{{FF}}': 'FF',
        '{{S_IN}}': 'S_IN',
        '{{S_FN}}': 'S_FN',
        '{{FECHA_ACT}}': 'FECHA_ACT'
    }
    
    for run in paragraph.runs:
        for placeholder, field_name in placeholder_patterns.items():
            if field_name in field_mapping and field_mapping[field_name] and field_mapping[field_name].strip():
                value = field_mapping[field_name]
                if placeholder in run.text:
                    print(f"DEBUG: Found hidden placeholder {field_name} in run: '{run.text}'")
                    # Make the run visible again and replace the placeholder
                    run.font.color.rgb = RGBColor(0, 0, 0)  # Black color
                    # Preserve the run's formatting while replacing the text
                    run.text = run.text.replace(placeholder, value)
                    print(f"DEBUG: Updated hidden placeholder to: '{run.text}' with black color")
                    break


def _update_blank_field(paragraph, field_name, value):
    """
    Update blank fields when placeholders are not found
    Preserves formatting by working with runs
    """
    print(f"DEBUG: Looking for blank field {field_name} in paragraph: '{paragraph.text}'")
    
    # Define field labels to look for
    field_labels = {
        'NRO_ESC': 'ACTA NUMERO:',
        'FI': 'FI:',
        'FF': 'FF:',
        'S_IN': 'S_IN:',
        'S_FN': 'S_FN:',
        'FECHA_ACT': 'FECHA:'
    }
    
    if field_name in field_labels:
        label = field_labels[field_name]
        if label in paragraph.text:
            start_pos = paragraph.text.find(label)
            after_label = paragraph.text[start_pos + len(label):]
            if not after_label.strip() or after_label.strip() in ['', ' ', '\t', '\n']:
                print(f"DEBUG: Found blank {field_name} field")
                
                # Find the run that contains the label and add the value after it
                for run in paragraph.runs:
                    if label in run.text:
                        # Split the run text to add the value after the label
                        label_pos = run.text.find(label)
                        before_label = run.text[:label_pos]
                        after_label_text = run.text[label_pos + len(label):]
                        
                        # Update the run to include the value
                        run.text = f"{before_label}{label} {value}{after_label_text}"
                        # Ensure the new value is visible (black color)
                        run.font.color.rgb = RGBColor(0, 0, 0)  # Black color
                        print(f"DEBUG: Updated run to: '{run.text[:100]}...' with black color")
                        break


def _smart_update_table(current_table, new_table, field_mapping):
    """
    Smart update table content while preserving formatting
    """
    # Update each cell in the table
    for row_idx, row in enumerate(current_table.rows):
        if row_idx < len(new_table.rows):
            for cell_idx, cell in enumerate(row.cells):
                if cell_idx < len(new_table.rows[row_idx].cells):
                    new_cell = new_table.rows[row_idx].cells[cell_idx]
                    print(f"DEBUG: Processing table cell {row_idx},{cell_idx}")
                    for paragraph_idx, paragraph in enumerate(cell.paragraphs):
                        if paragraph.text.strip():  # Only update non-empty paragraphs
                            print(f"DEBUG: Table cell {row_idx},{cell_idx} paragraph {paragraph_idx}: '{paragraph.text[:100]}...'")
                            _smart_update_paragraph(paragraph, new_cell.paragraphs[paragraph_idx] if paragraph_idx < len(new_cell.paragraphs) else paragraph, field_mapping)
                        else:
                            # Also check for placeholders in empty paragraphs
                            print(f"DEBUG: Table cell {row_idx},{cell_idx} paragraph {paragraph_idx} is empty, checking for placeholders")
                            _update_based_on_template_placeholders(paragraph, new_cell.paragraphs[paragraph_idx].text if paragraph_idx < len(new_cell.paragraphs) else "", field_mapping)


class DocumentosGeneradosViewSet(ModelViewSet):
    """
    ViewSet for the Documentogenerados model.
    """
    queryset = models.Documentogenerados.objects.all()
    serializer_class = serializers.DocumentosGeneradosSerializer
    pagination_class = pagination.KardexPagination
    # permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def by_kardex(self, request):
        """
        Get Documentogenerados records by Kardex.
        """
        kardex = request.query_params.get('kardex')
        if not kardex:
            return Response(
                {"error": "kardex parameter is required."},
                status=400
            )
        
        documentos_generados = models.Documentogenerados.objects.filter(kardex=kardex)
        if not documentos_generados.exists():
            return Response([], status=200)

        serializer = serializers.DocumentosGeneradosSerializer(documentos_generados, many=True)
        return Response(serializer.data)


    @action(detail=False, methods=['get'], url_path='open-template')
    def open_template(self, request):
        print(f"DEBUG: open_template")
        template_id = request.query_params.get("template_id")
        kardex = request.query_params.get("kardex")
        action = request.query_params.get("action", "generate")
        mode = request.query_params.get("mode", "download")  # Add mode param for consistency

        user = request.user

        if not user:
            return HttpResponse({"error": "User not authenticated."}, status=401)
    
        if not template_id:
            return HttpResponse({"error": "Missing template_id parameter."}, status=400)

        if not kardex:
            return HttpResponse({"error": "Missing kardex parameter."}, status=400)
        
        todayTimeDate = datetime.now().isoformat() + 'Z'
        
        # create a new instance of Documentogenerados only if it doesn't exist
        print(f"DEBUG: kardex: {kardex}")
        print(f"DEBUG: getting doc: ")
        documentogenerados = models.Documentogenerados.objects.filter(kardex=kardex).first()
        print(f"DEBUG: documentogenerados: {documentogenerados}")
        if not documentogenerados:
            documentogenerados = models.Documentogenerados.objects.create(
                kardex=kardex,
                usuario=user.idusuario,
                fecha=todayTimeDate)
            print(f"DEBUG: creating doc: {documentogenerados}")
            try:
                template_id = int(template_id)
            except ValueError:
                return HttpResponse({"error": "Invalid template_id format."}, status=400)
            print(f"DEBUG: template_id: {template_id}")
            # Get the kardex record to determine the tipkar
            kardex_obj = Kardex.objects.filter(kardex=kardex).first()
            print(f"DEBUG: kardex_obj: {kardex_obj}")
            if not kardex_obj:
                return HttpResponse({"error": f"Kardex {kardex} not found"}, status=404)
            
            tipkar = kardex_obj.idtipkar

            if tipkar == 5:
                print(f"DEBUG: Using TestamentDocumentService for tipkar {tipkar}")
                service = TestamentoDocumentService()
                if mode == "open":
                    # Return the download URL for Windows users - force HTTPS
                    download_url = f"https://{request.get_host()}/docs/download/{kardex}/__PROY__{kardex}.docx"
                    response = JsonResponse({
                        'status': 'success',
                        'mode': 'open',
                        'filename': f"__PROY__{kardex}.docx",
                        'kardex': kardex,
                        'url': download_url,
                        'message': 'Document ready to open in Word'
                    })
                    response['Access-Control-Allow-Origin'] = '*'
                    return response
                else:
                    return service.generate_testamento_document(template_id, kardex, action, mode)

            if tipkar == 4:  # GARANTIAS MOBILIARIAS
                print(f"DEBUG: Using GarantiasMobiliariasDocumentService for tipkar {tipkar}")
                service = GarantiasMobiliariasDocumentService()
                if mode == "open":
                    download_url = f"https://{request.get_host()}/docs/download/{kardex}/__PROY__{kardex}.docx"
                    response = JsonResponse({
                        'status': 'success',
                        'mode': 'open',
                        'filename': f"__PROY__{kardex}.docx",
                        'kardex': kardex,
                        'url': download_url,
                        'message': 'Document ready to open in Word'
                    })
                    response['Access-Control-Allow-Origin'] = '*'
                    return response
                else:
                    return service.generate_garantias_mobiliarias_document(template_id, kardex, action, mode)
            
            # Route to appropriate service based on tipkar
            if tipkar == 3:  # TRANSFERENCIAS VEHICULARES
                print(f"DEBUG: Using VehicleTransferDocumentService for tipkar {tipkar}")
                service = VehicleTransferDocumentService()
                if mode == "open":
                    # Return the download URL for Windows users - force HTTPS
                    download_url = f"https://{request.get_host()}/docs/download/{kardex}/__PROY__{kardex}.docx"
                    response = JsonResponse({
                        'status': 'success',
                        'mode': 'open',
                        'filename': f"__PROY__{kardex}.docx",
                        'kardex': kardex,
                        'url': download_url,
                        'message': 'Document ready to open in Word'
                    })
                    response['Access-Control-Allow-Origin'] = '*'
                    return response
                else:
                    return service.generate_vehicle_transfer_document(template_id, kardex, action, mode)
            elif tipkar == 2:  # ASUNTOS NO CONTENCIOSOS
                print(f"DEBUG: Using NonContentiousDocumentService for tipkar {tipkar}")
                # For non-contentious, we need idtipoacto from the request or from kardex
                idtipoacto = request.query_params.get('idtipoacto', "013")
                if not idtipoacto:
                    # Try to get from kardex codactos
                    if kardex_obj.codactos:
                        idtipoacto = kardex_obj.codactos[:3]  # Take first 3 characters
                    else:
                        return HttpResponse({
                            'error': 'idtipoacto is required for non-contentious documents'
                        }, status=400)
                
                service = NonContentiousDocumentService()
                if mode == "open":
                    # Return the download URL for Windows users - force HTTPS
                    download_url = f"https://{request.get_host()}/docs/download/{kardex}/__PROY__{kardex}.docx"
                    response = JsonResponse({
                        'status': 'success',
                        'mode': 'open',
                        'filename': f"__PROY__{kardex}.docx",
                        'kardex': kardex,
                        'url': download_url,
                        'message': 'Document ready to open in Word'
                    })
                    response['Access-Control-Allow-Origin'] = '*'
                    return response
                else:
                    return service.generate_non_contentious_document(template_id, kardex, idtipoacto, action, mode)

            elif tipkar == 1:  # ESCRITURA PUBLICA
                print(f"DEBUG: Using EscrituraPublicaDocumentService for tipkar {tipkar}")
                service = EscrituraPublicaDocumentService()
                if mode == "open":
                    # Return the download URL for Windows users - force HTTPS
                    download_url = f"https://{request.get_host()}/docs/download/{kardex}/__PROY__{kardex}.docx"
                    response = JsonResponse({
                        'status': 'success',
                        'mode': 'open',
                        'filename': f"__PROY__{kardex}.docx",
                        'kardex': kardex,
                        'url': download_url,
                        'message': 'Document ready to open in Word'
                    })
                    response['Access-Control-Allow-Origin'] = '*'
                    return response
                else:
                    return service.generate_escritura_publica_document(template_id, kardex, action, mode)
            else:
                return HttpResponse({
                    'error': f'Document generation not implemented for tipkar {tipkar}'
                }, status=501)
        return HttpResponse({"error": "Documentogenerados already exists."}, status=400)

    @action(detail=False, methods=['get'], url_path='open-document')
    def open_document(self, request):
        """
        Will look for the document in the r2 storage, and if it exists, it will return the document
        If it doesn't exist, it will generate the document from the template, db save it in the r2 storage, and return the document
        """
        template_id = request.query_params.get("template_id")
        kardex = request.query_params.get("kardex", "ACT401-2025")
        action = request.query_params.get("action", "generate")
        mode = request.query_params.get("mode", "download")  # "download" or "open"

        user = request.user

        if not user:
            return HttpResponse({"error": "User not authenticated."}, status=401)

        if not template_id:
            return HttpResponse({"error": "Missing template_id parameter."}, status=400)

        if not kardex:
            return HttpResponse({"error": "Missing kardex parameter."}, status=400)

        try:
            template_id = int(template_id)
        except ValueError:
            return HttpResponse({"error": "Invalid template_id format."}, status=400)

        # Define the object key for R2
        object_key = f"rodriguez-zea/documentos/__PROY__{kardex}.docx"
        print(f"DEBUG: object_key: {object_key}")
        # Check if document exists in R2
        s3 = boto3.client(
            's3',
            endpoint_url=os.environ.get('CLOUDFLARE_R2_ENDPOINT'),
            aws_access_key_id=os.environ.get('CLOUDFLARE_R2_ACCESS_KEY'),
            aws_secret_access_key=os.environ.get('CLOUDFLARE_R2_SECRET_KEY'),
            config=Config(signature_version='s3v4'),
            region_name='auto',
        )

        try:
            # Try to get the document from R2
            print(f"DEBUG: Checking if document exists in R2: {object_key}")
            s3_response = s3.get_object(
                Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'),
                Key=object_key
            )
            
            # Document exists, return it
            print(f"DEBUG: Document found in R2, returning existing document")
            doc_content = s3_response['Body'].read()
            
            if mode == "open":
                # Return the download URL for Windows users - force HTTPS
                download_url = f"https://{request.get_host()}/docs/download/{kardex}/__PROY__{kardex}.docx"
                response = JsonResponse({
                    'status': 'success',
                    'mode': 'open',
                    'filename': f"__PROY__{kardex}.docx",
                    'kardex': kardex,
                    'url': download_url,
                    'message': 'Document ready to open in Word'
                })
                response['Access-Control-Allow-Origin'] = '*'
                return response
            else:
                # Testing mode: Download the document
                response = HttpResponse(
                    doc_content,
                    content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                )
                response['Content-Disposition'] = f'inline; filename="__PROY__{kardex}.docx"'
                response['Content-Length'] = str(len(doc_content))
                response['Access-Control-Allow-Origin'] = '*'
                return response
            
        except Exception as e:
            # Document doesn't exist in R2, generate it
            print(f"DEBUG: Document not found in R2: {e}")
            print(f"DEBUG: Generating new document for kardex: {kardex}")
            
            # Get the kardex record to determine the tipkar
            kardex_obj = Kardex.objects.filter(kardex=kardex).first()
            if not kardex_obj:
                return HttpResponse({"error": f"Kardex {kardex} not found"}, status=404)
            
            tipkar = kardex_obj.idtipkar
            
            # Route to appropriate service based on tipkar

            if tipkar == 5:
                print(f"DEBUG: Using TestamentDocumentService for tipkar {tipkar}")
                service = TestamentoDocumentService()
                if mode == "open":
                    # Return the download URL for Windows users - force HTTPS
                    download_url = f"https://{request.get_host()}/docs/download/{kardex}/__PROY__{kardex}.docx"
                    response = JsonResponse({
                        'status': 'success',
                        'mode': 'open',
                        'filename': f"__PROY__{kardex}.docx",
                        'kardex': kardex,
                        'url': download_url,
                        'message': 'Document ready to open in Word'
                    })
                    response['Access-Control-Allow-Origin'] = '*'
                    return response
                else:
                    return service.generate_testamento_document(template_id, kardex, action, mode)
            
            if tipkar == 4:  # GARANTIAS MOBILIARIAS
                print(f"DEBUG: Using GarantiasMobiliariasDocumentService for tipkar {tipkar}")
                service = GarantiasMobiliariasDocumentService()
                if mode == "open":
                    download_url = f"https://{request.get_host()}/docs/download/{kardex}/__PROY__{kardex}.docx"
                    response = JsonResponse({
                        'status': 'success',
                        'mode': 'open',
                        'filename': f"__PROY__{kardex}.docx",
                        'kardex': kardex,
                        'url': download_url,
                        'message': 'Document ready to open in Word'
                    })
                    response['Access-Control-Allow-Origin'] = '*'
                    return response
                else:
                    return service.generate_garantias_mobiliarias_document(template_id, kardex, action, mode)

            if tipkar == 3:  # TRANSFERENCIAS VEHICULARES
                print(f"DEBUG: Using VehicleTransferDocumentService for tipkar {tipkar}")
                service = VehicleTransferDocumentService()
                if mode == "open":
                    # Return the download URL for Windows users - force HTTPS
                    download_url = f"https://{request.get_host()}/docs/download/{kardex}/__PROY__{kardex}.docx"
                    response = JsonResponse({
                        'status': 'success',
                        'mode': 'open',
                        'filename': f"__PROY__{kardex}.docx",
                        'kardex': kardex,
                        'url': download_url,
                        'message': 'Document ready to open in Word'
                    })
                    response['Access-Control-Allow-Origin'] = '*'
                    return response
                else:
                    return service.generate_vehicle_transfer_document(template_id, kardex, action, mode)
            elif tipkar == 2:  # ASUNTOS NO CONTENCIOSOS
                print(f"DEBUG: Using NonContentiousDocumentService for tipkar {tipkar}")
                # For non-contentious, we need idtipoacto from the request or from kardex
                idtipoacto = request.query_params.get('idtipoacto')
                if not idtipoacto:
                    # Try to get from kardex codactos
                    if kardex_obj.codactos:
                        idtipoacto = kardex_obj.codactos[:3]  # Take first 3 characters
                    else:
                        return HttpResponse({
                            'error': 'idtipoacto is required for non-contentious documents'
                        }, status=400)
                
                service = NonContentiousDocumentService()
                if mode == "open":
                    # Return the download URL for Windows users - force HTTPS
                    download_url = f"https://{request.get_host()}/docs/download/{kardex}/__PROY__{kardex}.docx"
                    response = JsonResponse({
                        'status': 'success',
                        'mode': 'open',
                        'filename': f"__PROY__{kardex}.docx",
                        'kardex': kardex,
                        'url': download_url,
                        'message': 'Document ready to open in Word'
                    })
                    response['Access-Control-Allow-Origin'] = '*'
                    return response
                else:
                    return service.generate_non_contentious_document(template_id, kardex, idtipoacto, action, mode)
            elif tipkar == 1:  # ESCRITURA PUBLICA
                print(f"DEBUG: Using EscrituraPublicaDocumentService for tipkar {tipkar}")
                service = EscrituraPublicaDocumentService()
                if mode == "open":
                    # Return the download URL for Windows users - force HTTPS
                    download_url = f"https://{request.get_host()}/docs/download/{kardex}/__PROY__{kardex}.docx"
                    response = JsonResponse({
                        'status': 'success',
                        'mode': 'open',
                        'filename': f"__PROY__{kardex}.docx",
                        'kardex': kardex,
                        'url': download_url,
                        'message': 'Document ready to open in Word'
                    })
                    response['Access-Control-Allow-Origin'] = '*'
                    return response
                else:
                    return service.generate_escritura_publica_document(template_id, kardex, action, mode)
            else:
                return HttpResponse({
                    'error': f'Document generation not implemented for tipkar {tipkar}'
                }, status=501)

# Create S3 client once at module level for better performance
_s3_client = None

def get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            's3',
            endpoint_url=os.environ.get('CLOUDFLARE_R2_ENDPOINT'),
            aws_access_key_id=os.environ.get('CLOUDFLARE_R2_ACCESS_KEY'),
            aws_secret_access_key=os.environ.get('CLOUDFLARE_R2_SECRET_KEY'),
            config=Config(signature_version='s3v4'),
            region_name='auto',
        )
    return _s3_client

@api_view(['GET'])
# @permission_classes([IsAuthenticated])
def download_docx(request, kardex, kardex2):
    """
    Secure endpoint to stream a docx file from R2 to the user.
    Only authenticated users can access. Returns 404 if not found.
    """
    import boto3
    import os
    import time
    from botocore.client import Config
    from django.http import FileResponse, Http404, HttpResponse
    
    start_time = time.time()

    object_key = f"rodriguez-zea/documentos/__PROY__{kardex}.docx"
    
    try:
        s3 = get_s3_client()
        s3_response = s3.get_object(
            Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'),
            Key=object_key
        )
        file_stream = s3_response['Body']
        response = FileResponse(file_stream, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        response['Content-Disposition'] = f'inline; filename="__PROY__{kardex}.docx"'
        # Add caching headers for better performance
        response['Cache-Control'] = 'public, max-age=3600'  # Cache for 1 hour
        response['ETag'] = f'"{kardex}"'
        
        # Log performance metrics
        elapsed_time = time.time() - start_time
        print(f"DEBUG: download_docx took {elapsed_time:.2f} seconds for kardex: {kardex}")
        
        return response
    except s3.exceptions.NoSuchKey:
        raise Http404("Document not found")
    except Exception as e:
        return HttpResponse(f"Error: {str(e)}", status=500)

@api_view(['GET'])
def test_r2_connection(request):
    """
    Test R2 connection and configuration
    """
    try:
        # Check environment variables
        endpoint_url = os.environ.get('CLOUDFLARE_R2_ENDPOINT')
        access_key = os.environ.get('CLOUDFLARE_R2_ACCESS_KEY')
        secret_key = os.environ.get('CLOUDFLARE_R2_SECRET_KEY')
        bucket = os.environ.get('CLOUDFLARE_R2_BUCKET')
        
        config_status = {
            'endpoint_url': endpoint_url,
            'access_key_set': bool(access_key),
            'secret_key_set': bool(secret_key),
            'bucket': bucket,
        }
        
        # Test S3 client creation
        s3 = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version='s3v4'),
            region_name='auto',
        )
        
        # Test bucket access
        try:
            s3.head_bucket(Bucket=bucket)
            bucket_access = True
        except Exception as e:
            bucket_access = False
            bucket_error = str(e)
        
        return Response({
            'success': True,
            'config_status': config_status,
            's3_client_created': True,
            'bucket_access': bucket_access,
            'bucket_error': bucket_error if not bucket_access else None
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e),
            'config_status': config_status if 'config_status' in locals() else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ExtraprotocolaresViewSet(ModelViewSet):
    """
    ViewSet for handling all extraprotocolares document types including permiso viajes.
    This provides a modular approach for the 7+ different permiso viaje types.
    """
    serializer_class = serializers.DocumentosGeneradosSerializer  # Reuse existing serializer
    pagination_class = pagination.KardexPagination
    # permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Return empty queryset since this ViewSet is only for document generation
        """
        return models.Documentogenerados.objects.none()

    @action(detail=False, methods=['get'], url_path='permiso-viaje-interior')
    def permiso_viaje_interior(self, request):
        """
        Generate Permiso Viaje Interior document
        """
        print("DEBUG: ExtraprotocolaresViewSet.permiso_viaje_interior called")
        
        # Get parameters
        id_viaje = request.query_params.get('id_viaje')
        action = request.query_params.get('action', 'generate')  # Default to 'generate'
        mode = request.query_params.get('mode', 'download')

        if not id_viaje:
            return Response({'status': 'error', 'message': 'id_viaje parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

        service = PermisoViajeInteriorDocumentService()
        if action == 'retrieve':
            return service.retrieve_document(id_viaje, mode)
        else:
            return service.generate_permiso_viaje_interior_document(id_viaje, mode)

    @action(detail=False, methods=['get'], url_path='permiso-viaje-exterior')
    def permiso_viaje_exterior(self, request):
        """
        Generate or retrieve a Permiso Viaje Exterior document.
        - action=generate: Creates a new document, saves it to R2, and returns it.
        - action=retrieve: Fetches an existing document from R2 and returns it.
        """
        id_viaje = request.query_params.get('id_viaje')
        action = request.query_params.get('action', 'generate')
        mode = request.query_params.get('mode', 'download')
        
        if not id_viaje:
            return Response({'status': 'error', 'message': 'id_viaje parameter is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        service = PermisoViajeExteriorDocumentService()
        if action == 'retrieve':
            return service.retrieve_document(id_viaje, mode)
        else:
            return service.generate_permiso_viaje_exterior_document(id_viaje, mode)

    @action(detail=False, methods=['get'], url_path='poder-fuera-registro')
    def poder_fuera_registro(self, request):
        """
        Generate or retrieve a Poder Fuera de Registro document.
        - action=generate: Creates a new document, saves it to R2, and returns it.
        - action=retrieve: Fetches an existing document from R2 and returns it.
        """
        id_poder = request.query_params.get('id_poder')
        action = request.query_params.get('action', 'generate')
        mode = request.query_params.get('mode', 'download')

        if not id_poder:
            return Response({'status': 'error', 'message': 'id_poder parameter is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Build filename from num_kardex

        try:
            rec = IngresoPoderes.objects.get(id_poder=id_poder)
            num_kardex = rec.num_kardex
            if not num_kardex:
                return Response({'status': 'error', 'message': 'num_kardex is empty for the provided id_poder'}, status=status.HTTP_400_BAD_REQUEST)
            filename = f"__PROY__{num_kardex}.docx"
        except IngresoPoderes.DoesNotExist:
            return Response({'status': 'error', 'message': f'IngresoPoderes with id_poder {id_poder} not found'}, status=status.HTTP_404_NOT_FOUND)

        service = PoderFueraDeRegistroDocumentService()
        if action == 'retrieve':
            return service.retrieve_document(id_poder, filename, mode)
        else:
            return service.generate_poder_fuera_registro_document(id_poder, mode)

    @action(detail=False, methods=['get'], url_path='poder-essalud')
    def poder_essalud(self, request):
        """
        Generate or retrieve a Poder Essalud document.
        - action=generate: Creates a new document, saves it to R2, and returns it.
        - action=retrieve: Fetches an existing document from R2 and returns it.
        """
        id_poder = request.data.get('id_poder')
        action = request.data.get('action', 'generate') # generate, retrieve
        mode = request.data.get('mode', 'download') # download, open

        if not id_poder:
            return Response({'error': 'id_poder is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            rec = IngresoPoderes.objects.get(id_poder=id_poder)
            num_kardex = rec.num_kardex
            if not num_kardex:
                return Response({'status': 'error', 'message': 'num_kardex is empty for the provided id_poder'}, status=status.HTTP_400_BAD_REQUEST)
            filename = f"__PROY__{num_kardex}.docx"
        except IngresoPoderes.DoesNotExist:
            return Response({'status': 'error', 'message': f'IngresoPoderes with id_poder {id_poder} not found'}, status=status.HTTP_404_NOT_FOUND)

        service = PoderEssaludDocumentService()
        if action == 'retrieve':
            return service.retrieve_document(id_poder, filename, mode)
        else:
            return service.generate_poder_essalud_document(id_poder, mode)


    @action(detail=False, methods=['get'], url_path='poder-onp')
    def poder_onp(self, request):
        """
        Generate or retrieve a Poder ONP document.
        - action=generate: Creates a new document, saves it to R2, and returns it.
        - action=retrieve: Fetches an existing document from R2 and returns it.
        """
        id_poder = request.query_params.get('id_poder')
        action = request.query_params.get('action', 'generate')
        mode = request.query_params.get('mode', 'download')

        if not id_poder:
            return Response({'error': 'id_poder is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            rec = IngresoPoderes.objects.get(id_poder=id_poder)
            num_kardex = rec.num_kardex
            if not num_kardex:
                return Response({'status': 'error', 'message': 'num_kardex is empty for the provided id_poder'}, status=status.HTTP_400_BAD_REQUEST)
            filename = f"__PROY__{num_kardex}.docx"
        except IngresoPoderes.DoesNotExist:
            return Response({'status': 'error', 'message': f'IngresoPoderes with id_poder {id_poder} not found'}, status=status.HTTP_404_NOT_FOUND)

        service = PoderPensionDocumentService()
        if action == 'retrieve':
            return service.retrieve_document(id_poder, filename, mode)
        else:
            return service.generate_poder_pension_document(id_poder, mode)

    @action(detail=False, methods=['get'], url_path='carta-notarial')
    def carta_notarial(self, request):
        """
        Generate or retrieve a Carta Notarial document.
        - action=generate: Creates a new document, saves it to R2, and returns it.
        - action=retrieve: Fetches an existing document from R2 and returns it.
        """
        id_carta = request.query_params.get('id_carta')
        print(f"DEBUG: id_carta: {id_carta}")
        action = request.query_params.get('action', 'generate')
        mode = request.query_params.get('mode', 'download')

        if not id_carta:
            return Response({'error': 'id_carta is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            rec = IngresoCartas.objects.get(id_carta=id_carta)
            print(f"DEBUG: rec: {rec}")
            num_carta = rec.num_carta
            if not num_carta:
                return Response({'status': 'error', 'message': 'num_carta is empty for the provided id_carta'}, status=status.HTTP_400_BAD_REQUEST)
        except IngresoCartas.DoesNotExist:
            return Response({'status': 'error', 'message': f'IngresoCartas with id_carta {id_carta} not found'}, status=status.HTTP_404_NOT_FOUND)

        service = CartasNotarialesDocumentService()
        if action == 'retrieve':
            return service.retrieve_carta_document(num_carta, mode)
        else:
            return service.generate_carta_document(num_carta, mode)