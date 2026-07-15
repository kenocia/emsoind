# -*- coding: utf-8 -*-

from odoo import fields, models


class EmsoindSaleOrderInvoice(models.Model):
    """Una fila por cada factura de cliente publicada vinculada a una OV."""

    _name = 'emsoind.sale.order.invoice'
    _description = 'Órdenes de venta facturadas'
    _auto = False
    _rec_name = 'invoice_name'
    _order = 'invoice_date desc, order_id desc, invoice_id desc'

    order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Orden de venta',
        readonly=True,
    )
    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Factura',
        readonly=True,
    )
    order_name = fields.Char(string='Número OV', readonly=True)
    invoice_name = fields.Char(string='Número de factura', readonly=True)
    invoice_date = fields.Date(string='Fecha de facturación', readonly=True)
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Cliente',
        readonly=True,
    )
    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Vendedor',
        readonly=True,
    )
    date_order = fields.Datetime(string='Fecha orden', readonly=True)
    amount_total = fields.Monetary(
        string='Total OV',
        currency_field='currency_id',
        readonly=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        readonly=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Cotización'),
            ('sent', 'Cotización enviada'),
            ('sale', 'Orden de venta'),
            ('cancel', 'Cancelado'),
        ],
        string='Estado OV',
        readonly=True,
    )

    def get_formview_action(self, access_uid=None):
        """Abrir la OV estándar aunque el listado sea por factura."""
        self.ensure_one()
        return self.order_id.get_formview_action(access_uid=access_uid)

    def _select(self):
        return """
            (am.id::bigint * 1000000 + so.id) AS id,
            so.id AS order_id,
            am.id AS invoice_id,
            so.name AS order_name,
            am.name AS invoice_name,
            am.invoice_date AS invoice_date,
            so.partner_id AS partner_id,
            so.user_id AS user_id,
            so.date_order AS date_order,
            so.amount_total AS amount_total,
            so.currency_id AS currency_id,
            so.company_id AS company_id,
            so.state AS state
        """

    def _from(self):
        return """
            sale_order so
            JOIN sale_order_line sol ON sol.order_id = so.id
            JOIN sale_order_line_invoice_rel rel ON rel.order_line_id = sol.id
            JOIN account_move_line aml ON aml.id = rel.invoice_line_id
            JOIN account_move am ON am.id = aml.move_id
        """

    def _where(self):
        return """
            am.move_type = 'out_invoice'
            AND am.state = 'posted'
            AND so.state NOT IN ('draft', 'sent', 'cancel')
        """

    def _group_by(self):
        return """
            so.id,
            am.id,
            so.name,
            am.name,
            am.invoice_date,
            so.partner_id,
            so.user_id,
            so.date_order,
            so.amount_total,
            so.currency_id,
            so.company_id,
            so.state
        """

    @property
    def _table_query(self):
        return f"""
            SELECT {self._select()}
              FROM {self._from()}
             WHERE {self._where()}
          GROUP BY {self._group_by()}
        """
