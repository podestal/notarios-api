def _subfijo(xx: str) -> str:
    xx = xx.strip()
    length = len(xx)
    if length in (1, 2, 3):
        return ""
    if length in (4, 5, 6):
        return "MIL"
    return ""


def numtoletras(total1) -> str:
    xarray = {
        0: "CERO",
        1: "UN",
        2: "DOS",
        3: "TRES",
        4: "CUATRO",
        5: "CINCO",
        6: "SEIS",
        7: "SIETE",
        8: "OCHO",
        9: "NUEVE",
        10: "DIEZ",
        11: "ONCE",
        12: "DOCE",
        13: "TRECE",
        14: "CATORCE",
        15: "QUINCE",
        16: "DIECISEIS",
        17: "DIECISIETE",
        18: "DIECIOCHO",
        19: "DIECINUEVE",
        20: "VEINTI",
        30: "TREINTA",
        40: "CUARENTA",
        50: "CINCUENTA",
        60: "SESENTA",
        70: "SETENTA",
        80: "OCHENTA",
        90: "NOVENTA",
        100: "CIENTO",
        200: "DOSCIENTOS",
        300: "TRESCIENTOS",
        400: "CUATROCIENTOS",
        500: "QUINIENTOS",
        600: "SEISCIENTOS",
        700: "SETECIENTOS",
        800: "OCHOCIENTOS",
        900: "NOVENCIENTOS",
    }

    total1 = str(total1).strip()
    xpos_punto = total1.find(".")
    xaux_int = total1
    xdecimales = "00"
    if xpos_punto != -1:
        if xpos_punto == 0:
            total1 = f"0{total1}"
            xpos_punto = total1.find(".")
        xaux_int = total1[:xpos_punto]
        xdecimales = f"{total1[xpos_punto + 1:]}00"[:2]

    xaux_int = xaux_int or "0"
    xcadena = ""
    xaux = xaux_int.zfill(18)

    for xz in range(3):
        chunk = xaux[xz * 6 : (xz + 1) * 6]
        xi = 0
        xlimite = 6
        while xi < xlimite:
            x3digitos = (xlimite - xi) * -1
            part = chunk[x3digitos:] if x3digitos else chunk
            if not part:
                break

            centena = part[:3] if len(part) >= 3 else part.zfill(3)
            if int(centena) >= 100:
                seek = xarray.get(int(centena))
                if seek:
                    sub = _subfijo(part)
                    if int(centena) == 100:
                        xcadena = f" {xcadena} CIEN {sub}"
                    else:
                        xcadena = f" {xcadena} {seek} {sub}"
                    xi = 6
                    continue
                seek = xarray.get(int(centena[0]) * 100)
                if seek:
                    xcadena = f" {xcadena} {seek}"

            decena = part[1:3] if len(part) >= 3 else part[-2:].zfill(2)
            if int(decena) >= 10:
                seek = xarray.get(int(decena))
                if seek:
                    sub = _subfijo(part)
                    if int(decena) == 20:
                        xcadena = f" {xcadena} VEINTE{sub}"
                    else:
                        xcadena = f" {xcadena} {seek} {sub}"
                    xi = 6
                    continue
                seek = xarray.get(int(decena[0]) * 10)
                if seek:
                    if int(decena[0]) * 10 == 20:
                        xcadena = f" {xcadena} {seek}"
                    else:
                        xcadena = f" {xcadena} {seek} Y "

            unidad = part[2] if len(part) == 3 else part[-1]
            if int(unidad) >= 1:
                seek = xarray.get(int(unidad))
                sub = _subfijo(part)
                xcadena = f" {xcadena} {seek} {sub}"

            xi += 3

        if xcadena.strip().endswith("ILLON"):
            xcadena += " DE"
        if xcadena.strip().endswith("ILLONES"):
            xcadena += " DE"

        chunk_trim = chunk.strip()
        if chunk_trim and int(chunk_trim) > 0:
            if xz == 0:
                xcadena += (
                    "UN BILLON " if chunk_trim == "1" else " BILLONES "
                )
            elif xz == 1:
                xcadena += (
                    "UN MILLON " if chunk_trim == "1" else " MILLONES"
                )
            elif xz == 2:
                total_float = float(total1)
                if total_float < 1:
                    xcadena = f"CERO CON {xdecimales}/100 SOLES"
                elif total_float < 2:
                    xcadena = f" CON {xdecimales}/100 UN SOL "
                else:
                    xcadena += f"  CON {xdecimales}/100 SOLES "

    xcadena = xcadena.replace("VEINTI ", "VEINTI")
    while "  " in xcadena:
        xcadena = xcadena.replace("  ", " ")
    xcadena = xcadena.replace("UN UN", "UN")
    xcadena = xcadena.replace("BILLON DE BILLONES", "BILLON DE")
    xcadena = xcadena.replace("BILLONES DE MILLONES", "BILLONES DE")
    xcadena = xcadena.replace("DE UN", "UN")
    return xcadena.strip()
