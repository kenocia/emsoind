# -*- coding: utf-8 -*-
from odoo import api, models
from odoo.tools.misc import formatLang


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.model
    def _split_printable_report_pages(
        self, line_list, recordset, first_cap=14, middle_cap=30, last_cap=18, single_cap=10,
    ):
        """Parte líneas PDF OC (header solo en 1.ª página → cupo alto en siguientes)."""
        n = len(line_list)
        empty = recordset.browse()
        if not n:
            return [empty]

        def _browse(chunk):
            return recordset.browse([line.id for line in chunk])

        if n <= single_cap:
            return [_browse(line_list)]

        pages = []
        idx = 0
        is_first = True
        while idx < n:
            rem = n - idx
            if is_first:
                if rem <= first_cap + 2:
                    pages.append(_browse(line_list[idx:]))
                    break
                take = first_cap
                is_first = False
            else:
                if rem <= middle_cap + 3:
                    pages.append(_browse(line_list[idx:]))
                    break
                take = middle_cap
            pages.append(_browse(line_list[idx:idx + take]))
            idx += take
        return pages

    def _get_purchase_report_pages(self):
        """Líneas imprimibles OC/RFQ sin secciones."""
        self.ensure_one()
        lines = self.order_line.filtered(lambda l: l.display_type != 'line_section')
        return self._split_printable_report_pages(
            list(lines),
            lines,
            first_cap=14,
            middle_cap=30,
            last_cap=18,
            single_cap=10,
        )

    def _purchase_report_show_discount(self):
        self.ensure_one()
        return bool(self.order_line.filtered(
            lambda l: not l.display_type and (l.discount or 0.0)
        ))

    def _purchase_format_amount(self, amount):
        self.ensure_one()
        return formatLang(
            self.env, amount, digits=2, currency_obj=self.currency_id,
        )

    @api.model
    def _purchase_line_display_name(self, line):
        """Descripción comercial sin código interno [DEFAULT_CODE]."""
        name = (line.name or '').strip()
        if name.startswith('['):
            end = name.find(']')
            if end > 1:
                name = name[end + 1:]
        return '\n'.join(
            part.strip() for part in name.splitlines() if part.strip()
        )

    def _get_purchase_tax_rows(self):
        """Filas de impuestos para totales del PDF."""
        self.ensure_one()
        tax_groups = {}
        for line in self.order_line.filtered(lambda l: not l.display_type):
            for tax in line.taxes_id:
                key = tax.id
                if key not in tax_groups:
                    tax_groups[key] = {
                        'label': tax.invoice_label or tax.name,
                        'amount': 0.0,
                    }
                # Aproximación por línea: impuestos de la línea
                taxes = line.taxes_id.compute_all(
                    line.price_unit,
                    currency=self.currency_id,
                    quantity=line.product_qty,
                    product=line.product_id,
                    partner=self.partner_id,
                    discount=line.discount,
                )
                for t in taxes.get('taxes', []):
                    if t.get('id') == tax.id:
                        tax_groups[key]['amount'] += t.get('amount', 0.0)
        return list(tax_groups.values())
