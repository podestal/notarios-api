from decimal import Decimal
from datetime import datetime


class NumberToLetterConverter:
    """
    Utility class to convert numbers to letters (Spanish)
    """
    
    def __init__(self):
        self.unidades = ['', 'UNO', 'DOS', 'TRES', 'CUATRO', 'CINCO', 'SEIS', 'SIETE', 'OCHO', 'NUEVE']
        self.decenas = ['', 'DIEZ', 'VEINTE', 'TREINTA', 'CUARENTA', 'CINCUENTA', 'SESENTA', 'SETENTA', 'OCHENTA', 'NOVENTA']
        self.especiales = {
            11: 'ONCE', 12: 'DOCE', 13: 'TRECE', 14: 'CATORCE', 15: 'QUINCE',
            16: 'DIECISÉIS', 17: 'DIECISIETE', 18: 'DIECIOCHO', 19: 'DIECINUEVE'
        }
        self.meses = [
            'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
            'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE'
        ]
    
    def number_to_letters(self, number: str) -> str:
        """
        Convert number to letters in Spanish
        """
        try:
            num = int(number)
            if num == 0:
                return 'CERO'
            return self._convert_number_to_letters(num)
        except:
            return number
    
    def _convert_number_to_letters(self, num: int) -> str:
        """
        Internal method to convert number to letters
        """
        if num < 10:
            return self.unidades[num]
        elif num < 20:
            return self.especiales.get(num, '')
        elif num < 100:
            decena = num // 10
            unidad = num % 10
            if unidad == 0:
                return self.decenas[decena]
            else:
                return f"{self.decenas[decena]} Y {self.unidades[unidad]}"
        elif num < 1000:
            centena = num // 100
            resto = num % 100
            if resto == 0:
                return f"{self.unidades[centena]}CIENTOS"
            else:
                return f"{self.unidades[centena]}CIENTOS {self._convert_number_to_letters(resto)}"
        elif num < 1000000:
            miles = num // 1000
            resto = num % 1000
            if miles == 1:
                return f"MIL {self._convert_number_to_letters(resto)}"
            else:
                return f"{self._convert_number_to_letters(miles)} MIL {self._convert_number_to_letters(resto)}"
        elif num < 1000000000:
            millones = num // 1000000
            resto = num % 1000000
            if millones == 1:
                return f"UN MILLÓN {self._convert_number_to_letters(resto)}"
            else:
                return f"{self._convert_number_to_letters(millones)} MILLONES {self._convert_number_to_letters(resto)}"
        else:
            return str(num)  # Simplified for demo
    
    def date_to_letters(self, date) -> str:
        """
        Convert date to letters in Spanish
        """
        # Handle both datetime objects and strings
        if isinstance(date, str):
            try:
                from datetime import datetime
                date = datetime.fromisoformat(date.replace('Z', '+00:00'))
            except:
                # If we can't parse the date, return a default
                return "UNO DE ENERO DEL DOS MIL VEINTICUATRO"
        
        if not hasattr(date, 'day'):
            return "UNO DE ENERO DEL DOS MIL VEINTICUATRO"
            
        dia = date.day or 1
        mes = self.meses[date.month - 1]
        anio = date.year
        
        return f"{self.number_to_letters(str(dia))} DE {mes} DEL {self.number_to_letters(str(anio))}"
    
    def money_to_letters(self, currency: str, amount: Decimal) -> str:
        """
        Convert money amount to letters
        """
        if currency == "PEN":
            return f"{self.number_to_letters(str(int(amount)))} SOLES CON {self.number_to_letters(str(int((amount % 1) * 100)))} CÉNTIMOS"
        elif currency == "USD":
            return f"{self.number_to_letters(str(int(amount)))} DÓLARES AMERICANOS CON {self.number_to_letters(str(int((amount % 1) * 100)))} CENTAVOS"
        else:
            return f"{self.number_to_letters(str(int(amount)))} {currency}" 