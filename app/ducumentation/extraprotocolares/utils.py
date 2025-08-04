class NumberToLetterConverter:
    """
    Utility class to convert numbers to letters (Spanish)
    """
    
    def __init__(self):
        self.unidades = ['', 'UNO', 'DOS', 'TRES', 'CUATRO', 'CINCO', 'SEIS', 'SIETE', 'OCHO', 'NUEVE']
        self.decenas = ['', 'DIEZ', 'VEINTE', 'TREINTA', 'CUARENTA', 'CINCUENTA', 'SESENTA', 'SETENTA', 'OCHENTA', 'NOVENTA']
        self.especiales = {
            11: 'ONCE', 12: 'DOCE', 13: 'TRECE', 14: 'CATORCE', 15: 'QUINCE',
            16: 'DIECISÉIS', 17: 'DIECISIETE', 18: 'DIECIOCHO', 19: 'DIECINUEVE',
            21: 'VEINTIUNO', 22: 'VEINTIDÓS', 23: 'VEINTITRÉS', 24: 'VEINTICUATRO',
            25: 'VEINTICINCO', 26: 'VEINTISÉIS', 27: 'VEINTISIETE', 28: 'VEINTIOCHO', 29: 'VEINTINUEVE'
        }
    
    def number_to_letters(self, number):
        """
        Convert a number to letters in Spanish
        """
        if number is None:
            return ''
        
        try:
            num = int(number)
            if num == 0:
                return 'CERO'
            elif num < 0:
                return f"MENOS {self._convert_positive(num * -1)}"
            else:
                return self._convert_positive(num)
        except (ValueError, TypeError):
            return str(number)
    
    def _convert_positive(self, num):
        """
        Convert positive numbers to letters
        """
        if num in self.especiales:
            return self.especiales[num]
        elif num < 10:
            return self.unidades[num]
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
            if centena == 1:
                if resto == 0:
                    return 'CIEN'
                else:
                    return f"CIENTO {self._convert_positive(resto)}"
            else:
                if resto == 0:
                    return f"{self.unidades[centena]}CIENTOS"
                else:
                    return f"{self.unidades[centena]}CIENTOS {self._convert_positive(resto)}"
        else:
            # For larger numbers, use a simpler approach
            return str(num)
    
    def date_to_letters(self, date_obj):
        """
        Convert a date to letters in Spanish
        """
        if date_obj is None:
            return ''
        
        try:
            from datetime import datetime
            if isinstance(date_obj, str):
                date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
            
            day = date_obj.day
            month = date_obj.month
            year = date_obj.year
            
            months = [
                '', 'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
                'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE'
            ]
            
            day_letters = self.number_to_letters(day)
            month_letters = months[month]
            year_letters = self.number_to_letters(year)
            
            return f"{day_letters} DE {month_letters} DEL AÑO {year_letters}"
        except Exception:
            return str(date_obj) 