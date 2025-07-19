# sisgen_service/utils/validators.py
from typing import Dict, List, Any
from datetime import datetime
from .exceptions import ValidationException

class SearchFiltersValidator:
    def __init__(self):
        self.valid_estados = [-1, 0, 1, 2, 3, 4, 5]
        self.valid_tipos_instrumento = [1, 2, 3, 4, 5]
    
    def validate(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate search filters
        Args:
            filters: Dictionary containing search filters
        Returns:
            Validated filters dictionary
        Raises:
            ValidationException: If validation fails
        """
        try:
            validated = {}
            
            # Validate required fields
            self._validate_required_fields(filters, validated)
            
            # Validate optional fields
            self._validate_optional_fields(filters, validated)
            
            # Validate date ranges
            self._validate_date_range(validated)
            
            # Validate numeric fields
            self._validate_numeric_fields(validated)
            
            return validated
            
        except Exception as e:
            raise ValidationException(f"Validation error: {str(e)}")
    
    def _validate_required_fields(self, filters: Dict[str, Any], validated: Dict[str, Any]):
        """Validate required fields"""
        required_fields = ['fechaDesde', 'fechaHasta', 'tipoInstrumento', 'estado']
        
        for field in required_fields:
            if field not in filters:
                raise ValidationException(f"Missing required field: {field}")
            
            value = filters[field]
            if value is None or value == '':
                raise ValidationException(f"Required field cannot be empty: {field}")
            
            validated[field] = value
    
    def _validate_optional_fields(self, filters: Dict[str, Any], validated: Dict[str, Any]):
        """Validate optional fields"""
        # codigoActo is optional, default to 0
        validated['codigoActo'] = filters.get('codigoActo', 0)
        
        # Validate codigoActo if provided
        if validated['codigoActo'] is not None:
            if not isinstance(validated['codigoActo'], (int, str)):
                raise ValidationException("codigoActo must be a number")
            
            try:
                validated['codigoActo'] = int(validated['codigoActo'])
                if validated['codigoActo'] < 0:
                    raise ValidationException("codigoActo must be non-negative")
            except (ValueError, TypeError):
                raise ValidationException("codigoActo must be a valid number")
    
    def _validate_date_range(self, validated: Dict[str, Any]):
        """Validate date format and range"""
        try:
            # Validate fechaDesde
            fecha_desde = self._parse_date(validated['fechaDesde'])
            validated['fechaDesde'] = fecha_desde.strftime('%Y-%m-%d')
            
            # Validate fechaHasta
            fecha_hasta = self._parse_date(validated['fechaHasta'])
            validated['fechaHasta'] = fecha_hasta.strftime('%Y-%m-%d')
            
            # Validate date range
            if fecha_desde > fecha_hasta:
                raise ValidationException("fechaDesde cannot be later than fechaHasta")
            
            # Validate date range is not too large (e.g., max 1 year)
            date_diff = fecha_hasta - fecha_desde
            if date_diff.days > 365:
                raise ValidationException("Date range cannot exceed 1 year")
                
        except ValueError as e:
            raise ValidationException(f"Invalid date format: {str(e)}")
    
    def _validate_numeric_fields(self, validated: Dict[str, Any]):
        """Validate numeric fields"""
        # Validate estado
        if not isinstance(validated['estado'], (int, str)):
            raise ValidationException("estado must be a number")
        
        try:
            validated['estado'] = int(validated['estado'])
            if validated['estado'] not in self.valid_estados:
                raise ValidationException(f"Invalid estado. Must be one of: {self.valid_estados}")
        except (ValueError, TypeError):
            raise ValidationException("estado must be a valid number")
        
        # Validate tipoInstrumento
        if not isinstance(validated['tipoInstrumento'], (int, str)):
            raise ValidationException("tipoInstrumento must be a number")
        
        try:
            validated['tipoInstrumento'] = int(validated['tipoInstrumento'])
            if validated['tipoInstrumento'] not in self.valid_tipos_instrumento:
                raise ValidationException(f"Invalid tipoInstrumento. Must be one of: {self.valid_tipos_instrumento}")
        except (ValueError, TypeError):
            raise ValidationException("tipoInstrumento must be a valid number")
    
    def _parse_date(self, date_value: Any) -> datetime:
        """Parse date value into datetime object"""
        if isinstance(date_value, datetime):
            return date_value
        
        if isinstance(date_value, str):
            # Try different date formats
            date_formats = ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d']
            
            for fmt in date_formats:
                try:
                    return datetime.strptime(date_value, fmt)
                except ValueError:
                    continue
            
            raise ValueError(f"Unable to parse date: {date_value}")
        
        raise ValueError(f"Invalid date type: {type(date_value)}")

class DocumentDataValidator:
    """Validator for document data"""
    
    def validate_document(self, document: Dict[str, Any]) -> bool:
        """Validate a single document"""
        required_fields = ['kardex', 'numescritura', 'fechaescritura', 'idtipkar']
        
        for field in required_fields:
            if field not in document or document[field] is None:
                raise ValidationException(f"Missing required field in document: {field}")
        
        return True
    
    def validate_document_list(self, documents: List[Dict[str, Any]]) -> bool:
        """Validate a list of documents"""
        if not isinstance(documents, list):
            raise ValidationException("Documents must be a list")
        
        for i, doc in enumerate(documents):
            try:
                self.validate_document(doc)
            except ValidationException as e:
                raise ValidationException(f"Document {i}: {str(e)}")
        
        return True

class XMLContentValidator:
    """Validator for XML content"""
    
    def validate_xml_content(self, xml_content: str) -> bool:
        """Validate XML content"""
        if not xml_content or not isinstance(xml_content, str):
            raise ValidationException("XML content must be a non-empty string")
        
        if len(xml_content.strip()) == 0:
            raise ValidationException("XML content cannot be empty")
        
        # Basic XML structure validation
        if not xml_content.strip().startswith('<'):
            raise ValidationException("XML content must start with a tag")
        
        return True