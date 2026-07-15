# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    kc_document_number = fields.Char(string='N° Documento / Correlativo')
    kc_document_type = fields.Selection(
        selection=[
            ('boleta', 'Boleta de Compra'),
            ('factura', 'Factura (CAI)'),
        ],
        string='Tipo de Documento Fiscal',
        default=lambda self: self._default_kc_document_type(),
    )
    kc_cai = fields.Char(string='CAI')
    kc_cai_required = fields.Boolean(
        compute='_compute_kc_cai_required',
        string='CAI requerido',
    )
    kc_document_date = fields.Date(
        string='Fecha de Emisión del Documento',
        help='Fecha real del documento del proveedor; puede diferir de la fecha contable.',
    )
    kc_vendor_bill_id = fields.Many2one(
        'account.move',
        string='Factura proveedor',
        copy=False,
        readonly=True,
    )
    kc_fund_move_id = fields.Many2one(
        'account.move',
        string='Asiento aplicación fondo',
        copy=False,
        readonly=True,
    )
    kc_is_fiscal_expense = fields.Boolean(
        compute='_compute_kc_is_fiscal_expense',
        string='Gasto con documento fiscal',
    )

    @api.depends('kc_document_number', 'kc_document_type')
    def _compute_kc_is_fiscal_expense(self):
        for expense in self:
            expense.kc_is_fiscal_expense = expense._kc_is_fiscal_expense()

    @api.model
    def _default_kc_document_type(self):
        company = self.env.company
        if getattr(company, 'tipo_contribuyente', 'pequeno') == 'pequeno':
            return 'boleta'
        return 'boleta'

    def _kc_is_fiscal_expense(self):
        self.ensure_one()
        return bool(self.kc_document_number or self.kc_document_type)

    @api.depends('kc_document_type', 'company_id', 'company_id.tipo_contribuyente')
    def _compute_kc_cai_required(self):
        for expense in self:
            company = expense.company_id or expense.env.company
            tipo = getattr(company, 'tipo_contribuyente', 'pequeno')
            expense.kc_cai_required = (
                expense.kc_document_type == 'factura'
                and tipo in ('mediano', 'grande')
            )

    @api.constrains('kc_document_type', 'kc_cai', 'company_id')
    def _check_cai_required(self):
        for expense in self:
            if not expense.kc_cai_required:
                continue
            if expense.kc_document_type == 'factura' and not expense.kc_cai:
                raise ValidationError(_(
                    'El CAI del proveedor es obligatorio para facturas formales '
                    'cuando la empresa es mediana o grande contribuyente.',
                ))

    @api.constrains('kc_document_number', 'kc_document_type', 'vendor_id')
    def _check_fiscal_vendor(self):
        for expense in self:
            if expense._kc_is_fiscal_expense() and not expense.vendor_id:
                raise ValidationError(_(
                    'El proveedor es obligatorio cuando el gasto tiene '
                    'documento fiscal (boleta o factura).',
                ))

    @api.constrains('vendor_id')
    def _check_vendor_rtn(self):
        for expense in self:
            vendor = expense.vendor_id
            if vendor and vendor.country_id.code == 'HN' and vendor.vat:
                vendor._validate_rtn_format()

    def _kc_fiscal_header_vals(self):
        """Valores SAR de cabecera derivados de este gasto."""
        self.ensure_one()
        document_date = self.kc_document_date or self.date
        femision = fields.Date.to_string(document_date) if document_date else ''
        return {
            'correlativo_proveedor': self.kc_document_number or '',
            'cai_proveedor': self.kc_cai or '',
            'femision_proveedor': femision,
            'class_document_sar': (
                'FA' if self.kc_document_type == 'factura' else 'OC'
            ),
            'montos_sar': 'gasto',
        }

    def _prepare_move_lines_vals(self):
        vals = super()._prepare_move_lines_vals()
        if self.payment_mode == 'own_account' and self.vendor_id:
            vals['partner_id'] = self.vendor_id.id
        return vals
