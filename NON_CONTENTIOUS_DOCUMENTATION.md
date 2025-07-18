# Unified Document Generation System

This document describes the implementation of a unified document generation system that automatically routes to the appropriate service based on the `tipkar` (tipo kardex) field from the kardex record.

## Overview

The unified document generation system allows users to generate legal documents based on the `tipkar` field from the kardex record. The system automatically routes to the appropriate service based on the document type.

## Features

- **Unified Document Generation**: Generate documents based on tipkar (1-5)
- **Automatic Routing**: System automatically selects the appropriate service
- **Smart Updates**: Update existing documents while preserving manual edits
- **R2 Storage Integration**: Templates and generated documents stored in Cloudflare R2
- **Contractor Management**: Handle transferors (P) and acquirers (C) with proper grammar
- **Payment Information**: Process payment methods and amounts
- **Escrituración Data**: Handle folios and papeles information

## Document Types by Tipkar

The system supports the following document types based on the `tipkar` field:

| Tipkar | Document Type | Abbreviation | Status |
|--------|---------------|--------------|---------|
| 1 | ESCRITURAS PUBLICAS | KAR | Not implemented |
| 2 | ASUNTOS NO CONTENCIOSOS | NCT | ✅ Implemented |
| 3 | TRANSFERENCIAS VEHICULARES | ACT | ✅ Implemented |
| 4 | GARANTIAS MOBILIARIAS | GAM | Not implemented |
| 5 | TESTAMENTOS | TES | Not implemented |

## API Endpoints

The system provides only **2 unified endpoints** that handle all document types automatically:

### Generate Document

**POST** `/api/ducumentation/generate-document/`

**Parameters:**
- `template_id` (required): ID of the template to use
- `kardex` (required): Kardex number
- `idtipoacto` (optional): Type of act ID (automatically extracted from kardex for non-contentious)
- `action` (optional): 'generate' or 'update' (default: 'generate')
- `mode` (optional): 'download' or 'preview' (default: 'download')

**Examples:**
```bash
# For vehicular documents (tipkar = 3)
curl -X POST http://localhost:8000/api/ducumentation/generate-document/ \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "template_id=1&kardex=ACT2024-001&action=generate&mode=download"

# For non-contentious documents (tipkar = 2)
curl -X POST http://localhost:8000/api/ducumentation/generate-document/ \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "template_id=1&kardex=NCT2024-001&action=generate&mode=download"
```

### Update Document

**POST** `/api/ducumentation/update-document/`

**Parameters:**
- `template_id` (required): ID of the template to use
- `kardex` (required): Kardex number
- `idtipoacto` (optional): Type of act ID (automatically extracted from kardex for non-contentious)

**Examples:**
```bash
# For vehicular documents (tipkar = 3)
curl -X POST http://localhost:8000/api/ducumentation/update-document/ \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "template_id=1&kardex=ACT2024-001"

# For non-contentious documents (tipkar = 2)
curl -X POST http://localhost:8000/api/ducumentation/update-document/ \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "template_id=1&kardex=NCT2024-001"
```

## Document Data Structure

The system processes the following data categories:

### 1. Document Information
- Kardex number
- Escritura number with letters
- User information
- Abogado information
- Dates and folios

### 2. Contractors (Transferors and Acquirers)
- Personal information (names, nationality, civil status)
- Document information (type, number)
- Address information
- Occupation
- Gender-specific grammar

### 3. Payment Information
- Amount and currency
- Payment method (cash, check, etc.)
- SUNAT payment codes
- Legal compliance text

### 4. Escrituración Data
- Initial and final folios
- Initial and final papeles

## Template Structure

Templates should be stored in R2 at:
`rodriguez-zea/PROTOCOLARES/ACTAS Y ESCRITURAS DE PROCEDIMIENTOS NO CONTENCIOSOS/`

Generated documents are stored at:
`rodriguez-zea/documentos/PROTOCOLARES/ACTAS Y ESCRITURAS DE PROCEDIMIENTOS NO CONTENCIOSOS/`

## Placeholders

The system supports the following placeholder types:

### Basic Placeholders
- `{{NRO_ESC}}` - Escritura number
- `{{FI}}` - Initial folio
- `{{FF}}` - Final folio
- `{{S_IN}}` - Initial papel
- `{{S_FN}}` - Final papel
- `{{FECHA_ACT}}` - Current date

### Contractor Placeholders
- `{{P_NOM_1}}` - First transferor name
- `{{C_NOM_1}}` - First acquirer name
- `{{P_DOC_1}}` - First transferor document
- `{{C_DOC_1}}` - First acquirer document
- And so on for up to 10 contractors each

### Payment Placeholders
- `{{MONTO}}` - Payment amount
- `{{MONTO_LETRAS}}` - Amount in letters
- `{{MED_PAGO}}` - Payment method description

## Implementation Details

### Service Classes

The system uses different service classes based on the `tipkar`:

#### `VehicleTransferDocumentService` (tipkar = 3)
- Handles vehicular transfer documents
- Uses vehicle-specific data extraction
- Templates stored in vehicular templates path

#### `NonContentiousDocumentService` (tipkar = 2)
- Handles non-contentious documents
- Uses contractor and payment data
- Templates stored in non-contentious templates path

### Automatic Routing

The system automatically routes to the appropriate service based on the `tipkar` field:
- **tipkar = 2**: Routes to `NonContentiousDocumentService`
- **tipkar = 3**: Routes to `VehicleTransferDocumentService`
- **Other tipkar values**: Returns 501 Not Implemented

### Key Methods

#### NonContentiousDocumentService
1. **`generate_non_contentious_document()`**: Main generation method
2. **`get_document_data()`**: Extract all required data
3. **`_get_contractors_data()`**: Process contractor information
4. **`_get_payment_data()`**: Handle payment information
5. **`remove_unfilled_placeholders()`**: Clean up unused placeholders

#### VehicleTransferDocumentService
1. **`generate_vehicle_transfer_document()`**: Main generation method
2. **`get_document_data()`**: Extract vehicle-specific data
3. **`_get_vehicle_data()`**: Process vehicle information
4. **`_get_contractors_data()`**: Process contractor information
5. **`remove_unfilled_placeholders()`**: Clean up unused placeholders

### Database Models Used

- `Kardex`: Main document information
- `Contratantesxacto`: Contractor relationships
- `Cliente2`: Contractor details
- `Patrimonial`: Payment information
- `TplTemplate`: Template information

## Error Handling

The system includes comprehensive error handling for:
- Missing required parameters
- Database connection issues
- R2 storage errors
- Template not found
- Invalid data formats

## Migration from PHP

This implementation is based on the legacy PHP code and maintains compatibility with:
- Same data structure
- Same placeholder system
- Same payment method logic
- Same contractor classification logic
- Automatic routing based on tipkar (replaces manual endpoint selection)

## Testing

To test the implementation:

1. Ensure you have valid templates in R2 storage
2. Create test kardex records with contractor data
3. Use the API endpoints to generate documents
4. Verify the generated documents match expected format

## Configuration

Required environment variables:
- `CLOUDFLARE_R2_ENDPOINT`
- `CLOUDFLARE_R2_ACCESS_KEY`
- `CLOUDFLARE_R2_SECRET_KEY`
- `CLOUDFLARE_R2_BUCKET` 