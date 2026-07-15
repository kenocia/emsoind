# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class KenociaPettyCashSettlement(models.TransientModel):
    _name = 'kenocia.petty.cash.settlement'
    _description = 'Wizard — Liquidación Caja Chica con Factura SAR'

    line_id = fields.Many2one(
        comodel_name='kenocia.petty.cash.line',
        string='Anticipo',
        required=True,
        readonly=True,
    )
    fund_id = fields.Many2one(
        comodel_name='kenocia.petty.cash',
        related='line_id.petty_cash_id',
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        related='line_id.petty_cash_id.company_id',
        readonly=True,
    )
    employee_id = fields.Many2one(
        related='line_id.employee_id',
        readonly=True,
    )
    amount_advance = fields.Monetary(
        string='Monto anticipo',
        related='line_id.amount',
        readonly=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Proveedor',
        domain="[('supplier_rank', '>', 0)]",
        help='Proveedores locales (HN) y del extranjero con facturas de compra publicadas.',
    )
    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Factura SAR',
        domain="[('move_type', '=', 'in_invoice'), ('state', '=', 'posted'), "
               "('payment_state', 'in', ('not_paid', 'partial'))]",
        help='Facturas publicadas y pendientes de pago del proveedor seleccionado.',
    )
    amount_invoice = fields.Monetary(
        string='Total factura',
        compute='_compute_invoice_amounts',
        readonly=True,
    )
    amount_tax = fields.Monetary(
        string='ISV',
        compute='_compute_invoice_amounts',
        readonly=True,
    )
    amount_untaxed = fields.Monetary(
        string='Base imponible',
        compute='_compute_invoice_amounts',
        readonly=True,
    )
    amount_diff = fields.Monetary(
        string='Vuelto al fondo',
        compute='_compute_amount_diff',
        currency_field='currency_id',
        help='Positivo: vuelto que regresa al fondo. Negativo: faltante.',
    )
    currency_id = fields.Many2one(
        related='line_id.currency_id',
    )
    settlement_date = fields.Date(
        string='Fecha liquidación',
        required=True,
        default=fields.Date.context_today,
    )

    # ── Contexto fiscal SAR (kc_fiscal_hn_v18) ──────────────────────────
    tipo_contribuyente = fields.Selection(
        related='company_id.tipo_contribuyente',
        readonly=True,
    )
    obligado_dmc = fields.Boolean(
        related='company_id.obligado_dmc',
        readonly=True,
    )
    nivel_control_fiscal = fields.Selection(
        related='company_id.nivel_control_fiscal',
        readonly=True,
    )
    vendor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Proveedor factura',
        related='invoice_id.partner_id',
        readonly=True,
    )
    vendor_rtn = fields.Char(
        related='partner_id.vat',
        readonly=True,
        string='RTN proveedor',
    )
    vendor_fiscal_label = fields.Char(
        compute='_compute_vendor_fiscal_label',
        readonly=True,
        string='Proveedor SAR',
    )
    invoice_document_fiscal = fields.Selection(
        related='invoice_id.journal_id.document_fiscal',
        readonly=True,
        string='Tipo documento fiscal',
    )
    invoice_correlativo = fields.Char(
        related='invoice_id.correlativo_proveedor',
        readonly=True,
        string='N° documento proveedor',
    )
    invoice_cai = fields.Char(
        related='invoice_id.cai_proveedor',
        readonly=True,
        string='CAI proveedor',
    )
    invoice_class_sar = fields.Selection(
        related='invoice_id.class_document_sar',
        readonly=True,
        string='Clase SAR',
    )
    invoice_seccion_dmc = fields.Selection(
        related='invoice_id.seccion_dmc',
        readonly=True,
        string='Sección DMC',
    )
    fiscal_compliance_ok = fields.Boolean(
        compute='_compute_fiscal_compliance',
        string='Cumple requisitos fiscales',
    )
    fiscal_compliance_message = fields.Html(
        compute='_compute_fiscal_compliance',
        readonly=True,
        string='Checklist fiscal',
    )

    @api.depends('invoice_id', 'invoice_id.partner_id', 'partner_id')
    def _compute_vendor_fiscal_label(self):
        for wizard in self:
            partner = wizard.partner_id or wizard.invoice_id.partner_id
            if partner:
                wizard.vendor_fiscal_label = partner._kenocia_get_fiscal_vendor_label()
            else:
                wizard.vendor_fiscal_label = False

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """Al cambiar proveedor, limpiar factura y acotar el selector."""
        self.invoice_id = False
        if self.partner_id:
            return {
                'domain': {
                    'invoice_id': [
                        ('move_type', '=', 'in_invoice'),
                        ('state', '=', 'posted'),
                        ('payment_state', 'in', ['not_paid', 'partial']),
                        ('partner_id', '=', self.partner_id.id),
                        ('company_id', '=', self.company_id.id),
                    ],
                },
            }
        return {'domain': {'invoice_id': [('id', '=', False)]}}

    @api.onchange('invoice_id')
    def _onchange_invoice_id(self):
        """Si llega factura primero, completar proveedor."""
        if self.invoice_id and not self.partner_id:
            self.partner_id = self.invoice_id.partner_id

    @api.depends('invoice_id', 'company_id.tipo_contribuyente', 'company_id.obligado_dmc')
    def _compute_fiscal_compliance(self):
        for wizard in self:
            if not wizard.invoice_id:
                wizard.fiscal_compliance_ok = False
                wizard.fiscal_compliance_message = _(
                    '<p class="text-muted mb-0">Seleccione una factura de proveedor '
                    'publicada y pendiente de pago.</p>'
                )
                continue
            errors = wizard.invoice_id._kenocia_get_petty_cash_fiscal_errors()
            wizard.fiscal_compliance_ok = not errors
            env = wizard.env
            tipo_labels = dict(
                env['res.company']._fields['tipo_contribuyente']._description_selection(env)
            )
            tipo_label = tipo_labels.get(wizard.tipo_contribuyente, '')
            nivel_labels = dict(
                env['res.company']._fields['nivel_control_fiscal']._description_selection(env)
            )
            nivel_label = nivel_labels.get(wizard.nivel_control_fiscal, '')
            items = [
                _(
                    '<li><strong>Empresa:</strong> %(tipo)s — '
                    'Control %(nivel)s</li>',
                    tipo=tipo_label,
                    nivel=nivel_label,
                ),
            ]
            if wizard.vendor_rtn:
                items.append(_(
                    '<li class="text-success">RTN proveedor: %(rtn)s</li>',
                    rtn=wizard.vendor_rtn,
                ))
            elif wizard.vendor_id and wizard.vendor_id.country_id.code == 'HN':
                items.append(_(
                    '<li class="text-danger">Proveedor hondureño sin RTN</li>',
                ))
            elif wizard.vendor_id and wizard.vendor_id.country_id.code != 'HN':
                items.append(_(
                    '<li class="text-info">Compra en el extranjero (%(country)s) — '
                    'sin requisitos CAI/correlativo local</li>',
                    country=wizard.vendor_id.country_id.name,
                ))
            doc_labels = dict(
                env['account.journal']._fields['document_fiscal']._description_selection(env)
            )
            doc_label = doc_labels.get(wizard.invoice_document_fiscal, '')
            if doc_label:
                items.append(_(
                    '<li>Documento: %(doc)s</li>',
                    doc=doc_label,
                ))
            for error in errors:
                items.append(_(
                    '<li class="text-danger">%(error)s</li>',
                    error=error,
                ))
            if not errors:
                items.append(_(
                    '<li class="text-success">'
                    'Factura lista para liquidación fiscal SAR</li>',
                ))
            wizard.fiscal_compliance_message = (
                '<ul class="mb-0 ps-3">' + ''.join(items) + '</ul>'
            )

    @api.depends(
        'invoice_id',
        'invoice_id.amount_total',
        'invoice_id.amount_tax',
        'invoice_id.amount_untaxed',
    )
    def _compute_invoice_amounts(self):
        for wizard in self:
            if wizard.invoice_id:
                wizard.amount_invoice = wizard.invoice_id.amount_total
                wizard.amount_tax = wizard.invoice_id.amount_tax
                wizard.amount_untaxed = wizard.invoice_id.amount_untaxed
            else:
                wizard.amount_invoice = 0.0
                wizard.amount_tax = 0.0
                wizard.amount_untaxed = 0.0

    @api.depends('amount_advance', 'amount_invoice')
    def _compute_amount_diff(self):
        for wizard in self:
            wizard.amount_diff = wizard.amount_advance - (wizard.amount_invoice or 0.0)

    @api.constrains('invoice_id', 'amount_advance', 'amount_invoice')
    def _check_invoice_amount(self):
        for wizard in self:
            if wizard.invoice_id and wizard.amount_invoice > wizard.amount_advance:
                raise ValidationError(_(
                    'El monto de la factura (%(invoice)s) '
                    'no puede superar el anticipo entregado (%(advance)s).\n'
                    'Si el gasto supera el anticipo, registre la diferencia '
                    'como un pago adicional desde Pagos CXP.',
                    invoice=wizard.currency_id.format(wizard.amount_invoice),
                    advance=wizard.currency_id.format(wizard.amount_advance),
                ))

    def action_confirm_settlement(self):
        self.ensure_one()
        line = self.line_id
        invoice = self.invoice_id
        fund = line.petty_cash_id

        if line.state != 'delivered':
            raise UserError(_('Solo anticipos entregados pueden liquidarse.'))
        if not self.partner_id:
            raise UserError(_('Debe seleccionar el proveedor del documento fiscal.'))
        if not invoice:
            raise UserError(_('Debe seleccionar una factura SAR.'))
        if invoice.partner_id != self.partner_id:
            raise UserError(_(
                'La factura seleccionada no pertenece al proveedor indicado.',
            ))
        invoice_total = invoice.amount_total
        if invoice_total <= 0:
            raise UserError(_('La factura no tiene monto válido.'))
        if invoice_total > self.amount_advance:
            raise UserError(_(
                'El monto de la factura (%(invoice)s) supera el anticipo entregado (%(advance)s).',
                invoice=line.currency_id.format(invoice_total),
                advance=line.currency_id.format(self.amount_advance),
            ))
        if invoice.currency_id != line.currency_id:
            raise UserError(_(
                'La moneda de la factura (%(invoice)s) no coincide con la del anticipo (%(advance)s).',
                invoice=invoice.currency_id.name,
                advance=line.currency_id.name,
            ))
        if invoice.company_id != fund.company_id:
            raise UserError(_(
                'La factura pertenece a otra compañía. '
                'Seleccione una factura de %(company)s.',
                company=fund.company_id.display_name,
            ))

        missing_sar = []
        is_hn_vendor = (
            invoice.partner_id.country_id
            and invoice.partner_id.country_id.code == 'HN'
        )
        if is_hn_vendor:
            if hasattr(invoice, 'correlativo_proveedor') and not invoice.correlativo_proveedor:
                missing_sar.append(_('Correlativo SAR'))
            if hasattr(invoice, 'cai_proveedor') and not invoice.cai_proveedor:
                missing_sar.append(_('CAI'))
        if missing_sar:
            line.message_post(
                body=_(
                    'Advertencia fiscal: la factura liquidada no tiene '
                    'completos los campos SAR: %(fields)s. '
                    'Verifique con Contabilidad.',
                    fields=', '.join(missing_sar),
                ),
                subtype_xmlid='mail.mt_note',
            )

        payment = self.env['account.payment'].with_context(
            kenocia_petty_cash=True,
        ).create({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': invoice.partner_id.id,
            'journal_id': fund.journal_id.id,
            'amount': invoice_total,
            'date': self.settlement_date,
            'memo': _(
                'Liquidación caja chica - %(emp)s - %(invoice)s',
                emp=line.employee_id.display_name,
                invoice=invoice.name or invoice.ref or str(invoice.id),
            ),
            'currency_id': line.currency_id.id,
            'petty_cash_line_id': line.id,
        })
        payment._kenocia_generate_and_post_move()
        if payment.state in ('draft', 'in_process'):
            payment.action_validate()

        payable_account = invoice.partner_id.with_company(
            invoice.company_id,
        ).property_account_payable_id
        payment_lines = payment.move_id.line_ids.filtered(
            lambda move_line: move_line.account_id == payable_account
            and not move_line.reconciled,
        )
        invoice_lines = invoice.line_ids.filtered(
            lambda move_line: move_line.account_id == payable_account
            and not move_line.reconciled,
        )
        if not payment_lines or not invoice_lines:
            raise UserError(_(
                'No se encontraron líneas por pagar para conciliar el pago con la factura.',
            ))
        (payment_lines + invoice_lines).reconcile()

        amount_returned = self.amount_advance - invoice_total
        line.write({
            'invoice_id': invoice.id,
            'amount_invoice': invoice_total,
            'amount_returned': amount_returned,
            'settlement_payment_id': payment.id,
            'move_settlement_id': payment.move_id.id,
            'settlement_date': self.settlement_date,
            'state': 'settled',
        })
        line.message_post(
            body=_(
                '<b>Anticipo liquidado.</b><br/>'
                'Factura: %(invoice)s | Proveedor: %(vendor)s<br/>'
                'Monto factura: %(invoice_amount)s | ISV: %(tax)s<br/>'
                'Anticipo entregado: %(advance)s | Vuelto al fondo: %(returned)s',
                invoice=invoice.display_name,
                vendor=invoice.partner_id.display_name,
                invoice_amount=line.currency_id.format(invoice_total),
                tax=line.currency_id.format(self.amount_tax or 0.0),
                advance=line.currency_id.format(self.amount_advance),
                returned=line.currency_id.format(amount_returned),
            ),
            subtype_xmlid='mail.mt_note',
        )
        fund.message_post(
            body=_(
                'Gasto liquidado: %(emp)s — %(concept)s — %(amount)s.',
                emp=line.employee_id.display_name,
                concept=line.description,
                amount=line.currency_id.format(invoice_total),
            ),
            subtype_xmlid='mail.mt_note',
        )
        invoice.message_post(
            body=_(
                'Factura pagada desde caja chica. Anticipo: <b>%(line)s</b>. '
                'Empleado: <b>%(emp)s</b>.',
                line=line.description,
                emp=line.employee_id.display_name,
            ),
            subtype_xmlid='mail.mt_note',
        )
        return {'type': 'ir.actions.act_window_close'}
