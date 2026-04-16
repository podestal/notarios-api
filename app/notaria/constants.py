import os

MONEDAS = {
    1: {'desmon': 'SOLES', 'simbolo': 'S/', 'codigo': 'PEN', 'codmon': '01'},
    2: {'desmon': 'DOLARES N.A.', 'simbolo': 'US$.', 'codigo': 'USD', 'codmon': '02'},
    3: {'desmon': 'EUROS', 'simbolo': '€', 'codigo': 'EUR', 'codmon': '03'},
}

OPORTUNIDADES_PAGO = {
    1: {'idoppago': 1, 'codoppago': '01', 'desoppago': 'A LA FIRMA DEL CONTRATO/MINUTA'},
    2: {'idoppago': 2, 'codoppago': '02', 'desoppago': 'A LA FIRMA DEL ACTA DE TRANSFERENCIA'},
    3: {'idoppago': 3, 'codoppago': '03', 'desoppago': 'A LA FIRMA DEL INSTRUMENTO PUBLICO NOTARIAL PROTOCOLAR'},
    4: {'idoppago': 4, 'codoppago': '04', 'desoppago': 'CONTRA LA INSCRIPCION DEL BLOQUEO REGISTRAL'},
    5: {'idoppago': 5, 'codoppago': '05', 'desoppago': 'CONTRA LA INSCRIPCION DE LA HIPOTECA'},
    6: {'idoppago': 6, 'codoppago': '06', 'desoppago': 'CON LA ENTREGA FISICA DEL BIEN'},
    7: {'idoppago': 7, 'codoppago': '07', 'desoppago': 'CON ANTERIORIDAD A LA FIRMA DE LA MINUTA'},
    8: {'idoppago': 8, 'codoppago': '99', 'desoppago': 'OTRO'},
    10: {'idoppago': 10, 'codoppago': '', 'desoppago': 'VACIO'}
}

FORMAS_PAGO = {
    '1': {'id_fpago': '1', 'codigo': 'C', 'descripcion': 'AL CONTADO'},
    '2': {'id_fpago': '2', 'codigo': 'P', 'descripcion': 'A PLAZOS (MAS DE UNA CUOTA)'},
    '3': {'id_fpago': '3', 'codigo': 'S', 'descripcion': 'SALDO PENDIENTE DE PAGO (UNA CUOTA)'},
    '4': {'id_fpago': '4', 'codigo': 'D', 'descripcion': 'DONACIONES O ANTICIPOS'},
    '5': {'id_fpago': '5', 'codigo': 'N', 'descripcion': 'NO APLICA'}
}


DEFAULT_KARDEX_ABBREVIATIONS = {
    '1': 'KAR',  # ESCRITURAS PUBLICAS
    '2': 'NCT',  # ASUNTOS NO CONTENCIOSOS
    '3': 'ACT',  # TRANSFERENCIAS VEHICULARES
    '4': 'GAM',  # GARANTIAS MOBILIARIAS
    '5': 'TES',  # TESTAMENTOS
}


def get_kardex_abbreviation_map():
    """
    Resolve kardex abbreviations from env.

    Example:
    KARDEX_ABBREVIATIONS=1:K,2:N,3:A,4:G,5:T
    """
    raw = (os.environ.get('KARDEX_ABBREVIATIONS') or '').strip()
    if not raw:
        return DEFAULT_KARDEX_ABBREVIATIONS.copy()

    parsed = DEFAULT_KARDEX_ABBREVIATIONS.copy()
    for entry in raw.split(','):
        entry = entry.strip()
        if not entry or ':' not in entry:
            continue
        key, value = entry.split(':', 1)
        key = key.strip()
        value = value.strip().upper()
        if key and value:
            parsed[key] = value
    return parsed
