# Extraprotocolares API Documentation

This document provides instructions on how to use the API endpoints available in the `ExtraprotocolaresViewSet`. These endpoints are designed to generate and retrieve various "permiso de viaje" (travel permit) documents.

## Base URL

All endpoints described here are relative to the base URL:
`/api/v1/extraprotocolares/`

---

## Endpoints

### 1. Permiso de Viaje al Interior

This endpoint handles the generation and retrieval of travel permits for minors traveling within the country.

**URL:** `permiso-viaje-interior/`  
**Method:** `GET`

#### Parameters

| Parameter  | Type   | Required | Default     | Description                                                                                             |
|------------|--------|----------|-------------|---------------------------------------------------------------------------------------------------------|
| `id_viaje` | `Int`  | **Yes**  | -           | The unique ID of the travel permit record from the database.                                            |
| `action`   | `String` | No       | `generate`  | Specifies the operation. Can be `generate` (creates a new file) or `retrieve` (fetches an existing file). |
| `mode`     | `String` | No       | `download`  | Specifies the response type. Can be `download` (returns the `.docx` file) or `open` (returns a JSON response with a temporary download URL). |

---

### 2. Permiso de Viaje al Exterior

This endpoint handles the generation and retrieval of travel permits for minors traveling outside the country.

**URL:** `permiso-viaje-exterior/`  
**Method:** `GET`

#### Parameters

The parameters are identical to the "Permiso de Viaje al Interior" endpoint.

| Parameter  | Type   | Required | Default     | Description                                                                                             |
|------------|--------|----------|-------------|---------------------------------------------------------------------------------------------------------|
| `id_viaje` | `Int`  | **Yes**  | -           | The unique ID of the travel permit record from the database.                                            |
| `action`   | `String` | No       | `generate`  | Specifies the operation. Can be `generate` (creates a new file) or `retrieve` (fetches an existing file). |
| `mode`     | `String` | No       | `download`  | Specifies the response type. Can be `download` (returns the `.docx` file) or `open` (returns a JSON response with a temporary download URL). |

---

## Usage Examples

Below are `curl` examples demonstrating how to use the API. Replace `YOUR_JWT_TOKEN`, `http://your-domain.com`, and `12345` with your actual JWT token, domain, and a valid `id_viaje`.

### Scenario 1: Generate a New Document and Download It

This is the default behavior. It creates a new document from the database, saves it to R2, and returns the file directly in the response.

```bash
# For Interior
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/permiso-viaje-interior/?id_viaje=12345" \
--output permiso_interior.docx

# For Exterior
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/permiso-viaje-exterior/?id_viaje=12345" \
--output permiso_exterior.docx
```
**Expected Response:** A `.docx` file download.

### Scenario 2: Retrieve an Existing Document for Download

This fetches a previously generated (and potentially manually edited) document from R2 and returns it for download.

```bash
# For Interior
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/permiso-viaje-interior/?id_viaje=12345&action=retrieve" \
--output permiso_interior_existente.docx

# For Exterior
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/permiso-viaje-exterior/?id_viaje=12345&action=retrieve" \
--output permiso_exterior_existente.docx
```
**Expected Response:** A `.docx` file download.

### Scenario 3: Generate a New Document and Get a URL to Open It

This generates a new document and returns a JSON response containing a secure, temporary URL that can be used to open the file for editing.

```bash
# For Interior
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/permiso-viaje-interior/?id_viaje=12345&mode=open"

# For Exterior
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/permiso-viaje-exterior/?id_viaje=12345&mode=open"
```
**Expected JSON Response:**
```json
{
    "status": "success",
    "mode": "open",
    "url": "https://<your-r2-bucket>....?X-Amz-Algorithm=...",
    "filename": "__PROY__2025000625.docx",
    "id_permiviaje": "12345",
    "message": "Document is ready to be opened."
}
```

### Scenario 4: Retrieve an Existing Document and Get a URL to Open It

This is ideal for when a user wants to continue editing a document they've previously saved. It retrieves the latest version from R2 and provides a URL to it.

```bash
# For Interior
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/permiso-viaje-interior/?id_viaje=12345&action=retrieve&mode=open"

# For Exterior
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/permiso-viaje-exterior/?id_viaje=12345&action=retrieve&mode=open"
```
**Expected JSON Response:** The same JSON structure as in Scenario 3, pointing to the existing file in R2. 

---

### 3. Carta Notarial (Certificación de Entrega)

This endpoint handles the generation and retrieval of Certificación de Entrega de Carta Notarial documents.

- URL: `carta-notarial/`  
- Method: `GET`

#### Parameters

| Parameter    | Type   | Required | Default     | Description                                                                 |
|--------------|--------|----------|-------------|-----------------------------------------------------------------------------|
| `id_carta`   | Int    | Yes      | -           | Primary key of the `IngresoCartas` record.                                   |
| `action`     | String | No       | `generate`  | `generate` to create a new file, `retrieve` to fetch an existing file.       |
| `mode`       | String | No       | `download`  | `download` to return `.docx` file, `open` to return a temporary pre-signed URL. |

#### Notes
- Output filename: `__CARTA__{num_carta}.docx` stored under R2 path `rodriguez-zea/documentos/`.
- 409 Conflict if generating when the document already exists.
- 404 Not Found if retrieving a document that does not exist in R2.

#### Usage Examples

- Generate and download:

```bash
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/carta-notarial/?id_carta=508" \
--output carta_notarial.docx
```

- Retrieve existing and download:

```bash
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/carta-notarial/?id_carta=508&action=retrieve" \
--output carta_notarial_existente.docx
```

- Generate/Retrieve and get open URL:

```bash
# Generate + open
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/carta-notarial/?id_carta=508&mode=open"

# Retrieve + open
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/carta-notarial/?id_carta=508&action=retrieve&mode=open"
```

---

### 4. Poderes

Endpoints to generate or retrieve Poder documents.

#### 4.1 Poder Fuera de Registro
- URL: `poder-fuera-registro/`  
- Method: `GET`

Parameters:

| Parameter   | Type   | Required | Default     | Description                                                                 |
|-------------|--------|----------|-------------|-----------------------------------------------------------------------------|
| `id_poder`  | Int    | Yes      | -           | Primary key of the `IngresoPoderes` record.                                   |
| `action`    | String | No       | `generate`  | `generate` to create a new file, `retrieve` to fetch an existing file.       |
| `mode`      | String | No       | `download`  | `download` to return `.docx` file, `open` to return a temporary pre-signed URL. |

- Output filename: `__PROY__{num_kardex}.docx`
- Template in R2: `PODER FUERA DE REGISTRO BASE.docx`
- 409 on duplicate generate; 404 on missing retrieve.

##### Usage Examples

- Generate and download:

```bash
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/poder-fuera-registro/?id_poder=315" \
--output poder_fuera_registro.docx
```

- Retrieve and download:

```bash
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/poder-fuera-registro/?id_poder=315&action=retrieve" \
--output poder_fuera_registro_existente.docx
```

- Open URL:

```bash
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/poder-fuera-registro/?id_poder=315&mode=open"
```

#### 4.2 Poder ESSALUD
- URL: `poder-essalud/`  
- Method: `GET`

Parameters: same as 4.1.

- Output filename: `__PROY__{num_kardex}.docx`
- Template in R2: `plantilla_poder_essalud.docx`
- 409 on duplicate generate; 404 on missing retrieve.

##### Usage Examples

```bash
# Generate and download
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/poder-essalud/?id_poder=315" \
--output poder_essalud.docx

# Retrieve and download
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/poder-essalud/?id_poder=315&action=retrieve" \
--output poder_essalud_existente.docx

# Open URL
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/poder-essalud/?id_poder=315&mode=open"
```

#### 4.3 Poder ONP (Pensión)
- URL: `poder-onp/`  
- Method: `GET`

Parameters: same as 4.1.

- Output filename: `__PROY__{num_kardex}.docx`
- Template in R2: `COBRO DE PENSION ONP.docx`
- 409 on duplicate generate; 404 on missing retrieve.

##### Usage Examples

```bash
# Generate and download
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/poder-onp/?id_poder=315" \
--output poder_onp.docx

# Retrieve and download
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/poder-onp/?id_poder=315&action=retrieve" \
--output poder_onp_existente.docx

# Open URL
curl -X GET -H "Authorization: JWT YOUR_JWT_TOKEN" \
"http://your-domain.com/api/v1/extraprotocolares/poder-onp/?id_poder=315&mode=open"
``` 