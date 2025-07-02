ROLE_LABELS = {
    'VENDEDOR':      {'M': 'VENDEDOR',      'F': 'VENDEDORA',      'M_PL': 'VENDEDORES',      'F_PL': 'VENDEDORAS'},
    'COMPRADOR':     {'M': 'COMPRADOR',     'F': 'COMPRADORA',     'M_PL': 'COMPRADORES',     'F_PL': 'COMPRADORAS'},
    'DONANTE':       {'M': 'DONANTE',       'F': 'DONANTE',        'M_PL': 'DONANTES',        'F_PL': 'DONANTES'},
    'DONATARIO':     {'M': 'DONATARIO',     'F': 'DONATARIA',      'M_PL': 'DONATARIOS',      'F_PL': 'DONATARIAS'},
    'APODERADO':     {'M': 'APODERADO',     'F': 'APODERADA',      'M_PL': 'APODERADOS',      'F_PL': 'APODERADAS'},
    'REPRESENTANTE': {'M': 'REPRESENTANTE', 'F': 'REPRESENTANTE',  'M_PL': 'REPRESENTANTES',  'F_PL': 'REPRESENTANTES'},
    'ADJUDICATARIO': {'M': 'ADJUDICATARIO', 'F': 'ADJUDICATARIA',  'M_PL': 'ADJUDICATARIOS',  'F_PL': 'ADJUDICATARIAS'},
    'ADJUDICANTE':   {'M': 'ADJUDICANTE',   'F': 'ADJUDICANTE',    'M_PL': 'ADJUDICANTES',    'F_PL': 'ADJUDICANTES'},
    'CEDENTE':       {'M': 'CEDENTE',       'F': 'CEDENTE',        'M_PL': 'CEDENTES',        'F_PL': 'CEDENTES'},
    'CESIONARIO':    {'M': 'CESIONARIO',    'F': 'CESIONARIA',     'M_PL': 'CESIONARIOS',     'F_PL': 'CESIONARIAS'},
    'ARRENDADOR':    {'M': 'ARRENDADOR',    'F': 'ARRENDADORA',    'M_PL': 'ARRENDADORES',    'F_PL': 'ARRENDADORAS'},
    'ARRENDATARIO':  {'M': 'ARRENDATARIO',  'F': 'ARRENDATARIA',   'M_PL': 'ARRENDATARIOS',   'F_PL': 'ARRENDATARIAS'},
    'MUTUANTE':      {'M': 'MUTUANTE',      'F': 'MUTUANTE',       'M_PL': 'MUTUANTES',       'F_PL': 'MUTUANTES'},
    'MUTUARIO':      {'M': 'MUTUARIO',      'F': 'MUTUARIA',       'M_PL': 'MUTUARIOS',       'F_PL': 'MUTUARIAS'},
    'CONYUGE':       {'M': 'CÓNYUGE',       'F': 'CÓNYUGE',        'M_PL': 'CÓNYUGES',        'F_PL': 'CÓNYUGES'},
    'TESTIGO':       {'M': 'TESTIGO',       'F': 'TESTIGO',        'M_PL': 'TESTIGOS',        'F_PL': 'TESTIGOS'},
    'OTORGANTE':     {'M': 'OTORGANTE',     'F': 'OTORGANTE',      'M_PL': 'OTORGANTES',      'F_PL': 'OTORGANTES'},
    'FIDEICOMITENTE':{'M': 'FIDEICOMITENTE','F': 'FIDEICOMITENTE', 'M_PL': 'FIDEICOMITENTES', 'F_PL': 'FIDEICOMITENTES'},
    'FIDEICOMISARIO':{'M': 'FIDEICOMISARIO','F': 'FIDEICOMISARIA', 'M_PL': 'FIDEICOMISARIOS', 'F_PL': 'FIDEICOMISARIAS'},
    'SOCIO':         {'M': 'SOCIO',         'F': 'SOCIA',          'M_PL': 'SOCIOS',          'F_PL': 'SOCIAS'},
    'ACCIONISTA':    {'M': 'ACCIONISTA',    'F': 'ACCIONISTA',     'M_PL': 'ACCIONISTAS',     'F_PL': 'ACCIONISTAS'},
    'ADMINISTRADOR': {'M': 'ADMINISTRADOR', 'F': 'ADMINISTRADORA', 'M_PL': 'ADMINISTRADORES', 'F_PL': 'ADMINISTRADORAS'},
}

TIPO_DOCUMENTO = {
    1: {'idtipdoc': 1, 'codtipdoc': '01', 'destipdoc': 'DOCUMENTO NACIONAL DE IDENTIDAD', 'td_abrev': 'DNI', 'sunat': 1},
    2: {'idtipdoc': 2, 'codtipdoc': '02', 'destipdoc': 'CARNET DE EXTRANJERIA', 'td_abrev': 'CE', 'sunat': 4},
    3: {'idtipdoc': 3, 'codtipdoc': '03', 'destipdoc': 'CARNET DE IDENTIDAD DE LAS FUERZAS POLICIALES', 'td_abrev': 'CEFP', 'sunat': 0},
    4: {'idtipdoc': 4, 'codtipdoc': '04', 'destipdoc': 'CARNET DE IDENTIDAD DE LAS FUERZAS ARMADAS', 'td_abrev': 'CEFA', 'sunat': 0},
    5: {'idtipdoc': 5, 'codtipdoc': '05', 'destipdoc': 'PASAPORTE', 'td_abrev': 'PASAPORTE', 'sunat': 7},
    6: {'idtipdoc': 6, 'codtipdoc': '06', 'destipdoc': 'CEDULA DE CIUDADANIA', 'td_abrev': 'CDC', 'sunat': 0},
    7: {'idtipdoc': 7, 'codtipdoc': '07', 'destipdoc': 'CEDULA DIPLOMATICA DE IDENTIDAD', 'td_abrev': 'CDI', 'sunat': 0},
    8: {'idtipdoc': 8, 'codtipdoc': '08', 'destipdoc': "R.U.C.", "td_abrev": "R.U.C.", "sunat": 6},
    9: {'idtipdoc': 9, 'codtipdoc': "09", "destipdoc": "OTRO", "td_abrev": "OTRO", "sunat": 0},
    10: {'idtipdoc': 10, 'codtipdoc': "10", "destipdoc": "SIN DOCUMENTO", "td_abrev": "SD", "sunat": 0},
    11: {'idtipdoc': 11, 'codtipdoc': "11", "destipdoc": "PARTIDA DE NACIMIENTO", "td_abrev": "PN", "sunat": 1}
}

CIVIL_STATUS = {
    0: {'value': 0, 'label': 'Seleccionar Estado Civil'},
    1: {'value': 1, 'label': 'Soltero'},
    2: {'value': 2, 'label': 'Casado'},
    3: {'value': 3, 'label': 'Divorciado'},
    4: {'value': 4, 'label': 'Viudo'},
    5: {'value': 5, 'label': 'Conviviente'},
}