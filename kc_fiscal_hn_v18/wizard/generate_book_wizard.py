# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.fiscal_period import check_fiscal_period, month_bounds


class GenerateBookWizard(models.TransientModel):
    _name = 'kc_fiscal_hn.wizard.generate_book'
    _description = 'Generar libro fiscal SAR desde facturas'

    book_type = fields.Selection(
        [
            ('sales', 'Libro de Ventas'),
            ('purchases', 'Libro de Compras (DMC)'),
            ('retentions', 'Libro de Retenciones'),
            ('exemptions', 'Libro de Exoneraciones'),
        ],
        string='Libro',
        required=True,
        default='sales',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(string='Desde', required=True, default=fields.Date.context_today)
    date_to = fields.Date(string='Hasta', required=True, default=fields.Date.context_today)
    replace_existing = fields.Boolean(
        string='Reemplazar líneas del mismo período',
        help='Elimina las líneas existentes del período antes de generar.',
    )

    @api.onchange('date_from')
    def _onchange_date_from_period(self):
        if self.date_from:
            self.date_from, self.date_to = month_bounds(self.date_from)

    @api.onchange('date_to')
    def _onchange_date_to_period(self):
        if self.date_from and self.date_to:
            if (
                self.date_from.year != self.date_to.year
                or self.date_from.month != self.date_to.month
            ):
                _, self.date_to = month_bounds(self.date_from)

    def action_generar(self):
        self.ensure_one()
        check_fiscal_period(self.date_from, self.date_to)
        mapping = {
            'sales': 'kc_fiscal_hn.book.sales',
            'purchases': 'kc_fiscal_hn.book.purchases',
            'retentions': 'kc_fiscal_hn.book.retentions',
            'exemptions': 'kc_fiscal_hn.book.exemptions',
        }
        model = mapping[self.book_type]
        return self.env[model].action_generar_desde_facturas(
            self.date_from,
            self.date_to,
            company_id=self.company_id.id,
            replace=self.replace_existing,
        )
