# -*- coding: utf-8 -*-

import re
import unicodedata

from odoo import api, models


class CustomTechnicalValueMixin(models.AbstractModel):
    """Utilidades compartidas para valores técnicos en líneas y lotes."""

    _name = 'custom.technical.value.mixin'
    _description = 'Mixin valores técnicos'

    @api.model
    def _normalize_token(self, value):
        """Normaliza un valor para clave técnica o nombre de lote."""
        if value is None or value is False:
            return ''
        text = str(value).strip().upper()
        text = unicodedata.normalize('NFKD', text)
        text = ''.join(c for c in text if not unicodedata.combining(c))
        text = re.sub(r'[^A-Z0-9]+', '', text)
        return text

    @api.model
    def _format_display_value(self, tech_value):
        """Texto legible de un registro de valor técnico."""
        attr = tech_value.attribute_id
        if attr.display_type == 'numeric':
            if tech_value.value_number is not False and tech_value.value_number is not None:
                num = tech_value._format_number(tech_value.value_number)
                if tech_value.uom_id:
                    return f'{num} {tech_value.uom_id.name}'
                return num
            return ''
        if tech_value.value_id:
            return tech_value.value_id.name
        return tech_value.value_text or ''

    @api.model
    def _format_key_value(self, tech_value):
        """Valor normalizado para technical_key."""
        attr = tech_value.attribute_id
        code = (attr.code or attr.name or '').strip().upper()
        if attr.display_type == 'numeric':
            if tech_value.value_number is None or tech_value.value_number is False:
                return code, ''
            num = tech_value._format_number(tech_value.value_number)
            if tech_value.uom_id:
                uom = self._normalize_token(tech_value.uom_id.name)
                return code, f'{self._normalize_token(num)}{uom}'
            return code, self._normalize_token(num)
        if tech_value.value_id:
            raw = tech_value.value_id.code or tech_value.value_id.name
            return code, self._normalize_token(raw)
        return code, self._normalize_token(tech_value.value_text)

    @api.model
    def _format_number(self, number):
        if number == int(number):
            return str(int(number))
        return str(number).rstrip('0').rstrip('.')

    @api.model
    def build_technical_description(self, technical_values):
        lines = []
        for tv in technical_values.sorted('sequence'):
            display = self._format_display_value(tv)
            if display:
                lines.append(f'{tv.attribute_id.name}: {display}')
        return ', '.join(lines)

    @api.model
    def build_technical_key(self, technical_values):
        parts = []
        for tv in technical_values.sorted('sequence'):
            code, val = self._format_key_value(tv)
            if code and val:
                parts.append(f'{code}={val}')
        return '|'.join(parts)

    @api.model
    def build_selection_key(self, technical_values):
        """Clave técnica considerando solo atributos de selección/radio.

        La matriz de configuraciones (`product.technical.configuration`) se
        genera únicamente con atributos enumerables (selección/radio); los
        numéricos/texto se omiten. Para validar que una combinación existe en la
        matriz se compara solo esta porción.
        """
        parts = []
        for tv in technical_values.sorted('sequence'):
            if tv.attribute_id.display_type not in ('selection', 'radio'):
                continue
            code, val = self._format_key_value(tv)
            if code and val:
                parts.append(f'{code}={val}')
        return '|'.join(parts)

    @api.model
    def build_lot_specs_compact(self, technical_values, max_len=24):
        """Valores técnicos concatenados sin separador (ej. Perfil 2 + Ancho 4 → 24)."""
        parts = []
        for tv in technical_values.sorted('sequence'):
            _, val = self._format_key_value(tv)
            if val:
                parts.append(val[:12])
        segment = ''.join(parts)
        segment = re.sub(r'[^A-Z0-9]', '', segment.upper())
        return segment[:max_len]

    @api.model
    def build_lot_name(self, product_code, technical_values, order_name=None,
                       date_str=None, sequence=None):
        """
        Nomenclatura: {REF}_{VALORES_CARACTERISTICAS}_{PEDIDO}
        Ejemplo: BTELGC16_44_S00042

        Los valores de características son los seteados en el wizard de
        configuración del producto (compactados). El pedido identifica el
        origen del lote. Si no se indica `order_name`, se conserva el patrón
        antiguo basado en fecha/secuencia como respaldo.
        """
        code = self.normalize_lot_name_part(product_code or 'X', max_len=12).replace('-', '')
        specs = self.build_lot_specs_compact(technical_values)
        if order_name:
            order_part = self.normalize_lot_name_part(order_name, max_len=20).replace('-', '')
            name = f'{code}_{specs}_{order_part}'
        else:
            if not date_str:
                from datetime import date
                date_str = date.today().strftime('%Y%m%d')
            if not sequence:
                sequence = '0001'
            name = f'{code}{specs}_{date_str}_{sequence}'
        return re.sub(r'[^A-Z0-9_]', '', name.upper())[:80]

    @api.model
    def normalize_lot_name_part(self, text, max_len=20):
        if not text:
            return 'X'
        text = unicodedata.normalize('NFKD', str(text))
        text = ''.join(c for c in text if not unicodedata.combining(c))
        text = text.upper().strip()
        text = re.sub(r'[^A-Z0-9]+', '-', text)
        text = re.sub(r'-+', '-', text).strip('-')
        return (text or 'X')[:max_len]
