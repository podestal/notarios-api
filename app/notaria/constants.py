MONEDAS = {
    1: {'desmon': 'SOLES', 'simbolo': 'S/', 'codigo': 'PEN', 'codmon': '01'},
    2: {'desmon': 'DOLARES N.A.', 'simbolo': 'US$.', 'codigo': 'USD', 'codmon': '02'},
    3: {'desmon': 'EUROS', 'simbolo': '€', 'codigo': 'EUR', 'codmon': '03'},
}


# | idoppago | codoppago | desoppago                                              |
# +----------+-----------+--------------------------------------------------------+
# |        1 | 01        | A LA FIRMA DEL CONTRATO/MINUTA                         |
# |        2 | 02        | A LA FIRMA DEL ACTA DE TRANSFERENCIA                   |
# |        3 | 03        | A LA FIRMA DEL INSTRUMENTO PUBLICO NOTARIAL PROTOCOLAR |
# |        4 | 04        | CONTRA LA INSCRIPCION DEL BLOQUEO REGISTRAL            |
# |        5 | 05        | CONTRA LA INSCRIPCION DE LA HIPOTECA                   |
# |        6 | 06        | CON LA ENTREGA FISICA DEL BIEN                         |
# |        7 | 07        | CON ANTERIORIDAD A LA FIRMA DE LA MINUTA               |
# |        8 | 99        | OTRO                                                   |
# |       10 |           | VACIO


# |        1 | C      | AL CONTADO                          |
# |        2 | P      | A PLAZOS (MAS DE UNA CUOTA)         |
# |        3 | S      | SALDO PENDIENTE DE PAGO (UNA CUOTA) |
# |        4 | D      | DONACIONES O ANTICIPOS              |
# |        5 | N      | NO APLICA