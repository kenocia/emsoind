# -*- coding: utf-8 -*-

from odoo import fields, models


class BookPurchases(models.Model):
    _inherit = 'kc_fiscal_hn.book.purchases'

    def _libro_proveedor_partner(self, move, expense=None):
        if expense and expense.vendor_id:
            return expense.vendor_id
        return super()._libro_proveedor_partner(move, expense=expense)

    def _iter_libro_compras_sources(self, move):
        if move.expense_sheet_id:
            for expense in move.expense_sheet_id.expense_line_ids:
                yield expense
            return
        yield from super()._iter_libro_compras_sources(move)

    def _libro_numero_documento(self, move, expense=None):
        if expense and expense.kc_document_number:
            return expense.kc_document_number.strip()
        return super()._libro_numero_documento(move, expense=expense)

    def _libro_line_amounts(self, move, expense=None):
        if not expense:
            return super()._libro_line_amounts(move, expense=expense)

        gravado_15 = gravado_18 = isv_15 = isv_18 = 0.0
        exento = exonerado = 0.0
        base_amount = expense.total_amount - expense.tax_amount
        for tax in expense.tax_ids:
            if getattr(tax, 'tipo_impuesto', None) == 'exento':
                exento += base_amount
            elif getattr(tax, 'tipo_impuesto', None) == 'exonerado':
                exonerado += base_amount
            elif tax.amount == 15:
                gravado_15 += base_amount
                isv_15 += expense.tax_amount
            elif tax.amount == 18:
                gravado_18 += base_amount
                isv_18 += expense.tax_amount

        if not expense.tax_ids:
            gravado_15 = base_amount

        clase = 'FA' if expense.kc_document_type == 'factura' else 'OC'
        document_date = expense.kc_document_date or expense.date
        femision = fields.Date.to_string(document_date) if document_date else ''

        tipo_compra = 'fa_gravada_15'
        if expense.kc_document_type == 'boleta':
            tipo_compra = 'boleta'
        elif gravado_18:
            tipo_compra = 'fa_gravada_18'
        elif exento:
            tipo_compra = 'fa_exenta' if clase == 'FA' else 'oc_exenta'
        elif exonerado:
            tipo_compra = 'fa_exonerada'
        elif clase == 'OC':
            tipo_compra = 'oc_gravada'

        return {
            'exento': exento,
            'exonerado': exonerado,
            'gravado_15': gravado_15,
            'isv_15': isv_15,
            'gravado_18': gravado_18,
            'isv_18': isv_18,
            'amount_total': expense.total_amount,
            'costo': 0.0,
            'gasto': expense.total_amount,
            'no_deducible': 0.0,
            'clase_documento': clase,
            'cai_proveedor': expense.kc_cai or '',
            'fecha_emision': femision,
            'tipo_compra_dmc': tipo_compra,
        }
