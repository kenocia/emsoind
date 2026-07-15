# -*- coding: utf-8 -*-
"""Utilidades puras de conversión numérica a texto para documentos fiscales SAR."""


class NumberUtilities:
    """Convierte montos numéricos a su representación en letras (Lempiras)."""

    _INDICADORES = (
        ("", ""),
        ("MIL", "MIL"),
        ("MILLON", "MILLONES"),
        ("MIL", "MIL"),
        ("BILLON", "BILLONES"),
    )

    _CENTENAS = (
        "",
        ("CIEN", "CIENTO"),
        "DOSCIENTOS",
        "TRESCIENTOS",
        "CUATROCIENTOS",
        "QUINIENTOS",
        "SEISCIENTOS",
        "SETECIENTOS",
        "OCHOCIENTOS",
        "NOVECIENTOS",
    )

    _DECENAS = (
        "",
        (
            "DIEZ",
            "ONCE",
            "DOCE",
            "TRECE",
            "CATORCE",
            "QUINCE",
            "DIECISEIS",
            "DIECISIETE",
            "DIECIOCHO",
            "DIECINUEVE",
        ),
        ("VEINTE", "VEINTI"),
        ("TREINTA", "TREINTA Y "),
        ("CUARENTA", "CUARENTA Y "),
        ("CINCUENTA", "CINCUENTA Y "),
        ("SESENTA", "SESENTA Y "),
        ("SETENTA", "SETENTA Y "),
        ("OCHENTA", "OCHENTA Y "),
        ("NOVENTA", "NOVENTA Y "),
    )

    _UNIDADES = (
        "",
        ("UN", "UNO"),
        "DOS",
        "TRES",
        "CUATRO",
        "CINCO",
        "SEIS",
        "SIETE",
        "OCHO",
        "NUEVE",
    )

    def numero_to_letras(self, numero: float) -> str:
        """Convierte un monto a letras en formato SAR Honduras.

        Ejemplo: 1150.00 → 'MIL CIENTO CINCUENTA LEMPIRAS Y CERO CENTAVOS EXACTOS'
        """
        entero = int(numero)
        decimal = int(round((numero - entero) * 100))
        contador = 0
        numero_letras = ""

        while entero > 0:
            cifra = entero % 1000
            en_letras = self.convierte_cifra(cifra, 1 if contador == 0 else 0).strip()
            indicador_singular, indicador_plural = self._INDICADORES[contador]

            if cifra == 0:
                numero_letras = f"{en_letras} {numero_letras}"
            elif cifra == 1 and contador in (1, 3):
                numero_letras = f"{indicador_singular} {numero_letras}"
            elif cifra == 1:
                numero_letras = f"{en_letras} {indicador_singular} {numero_letras}"
            else:
                numero_letras = f"{en_letras} {indicador_plural} {numero_letras}"

            numero_letras = numero_letras.strip()
            contador += 1
            entero //= 1000

        if not numero_letras:
            numero_letras = "CERO"

        centavos_letras = self.convierte_cifra(decimal, 1).strip() if decimal else "CERO"
        return f"{numero_letras} LEMPIRAS Y {centavos_letras} CENTAVOS EXACTOS"

    def convierte_cifra(self, numero: int, sw: int) -> str:
        """Convierte una cifra de hasta tres dígitos a su representación textual."""
        centena = numero // 100
        decena = (numero - centena * 100) // 10
        unidad = numero - centena * 100 - decena * 10

        texto_centena = self._CENTENAS[centena]
        if centena == 1:
            texto_centena = texto_centena[1] if decena + unidad else texto_centena[0]

        texto_decena = self._DECENAS[decena]
        if decena == 1:
            texto_decena = texto_decena[unidad]
        elif decena > 1:
            texto_decena = texto_decena[1] if unidad else texto_decena[0]

        texto_unidad = ""
        if decena != 1:
            texto_unidad = self._UNIDADES[unidad]
            if unidad == 1:
                texto_unidad = texto_unidad[sw]

        return f"{texto_centena} {texto_decena} {texto_unidad}".strip()
