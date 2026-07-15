# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class KenociaAdvancePayment(models.Model):
    _name = 'kenocia.advance.payment'
    _description = 'Pago Anticipado KENOCIA'
    _order = 'date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Referencia',
        default='/',
        copy=False,
        required=True,
        tracking=True,
    )
    advance_type = fields.Selection(
        selection=[
            ('customer', 'Adelanto Cliente (CXC)'),
            ('supplier', 'Adelanto Proveedor (CXP)'),
        ],
        string='Tipo de adelanto',
        required=True,
        index=True,
        tracking=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Contacto',
        required=True,
        index=True,
        tracking=True,
    )
    sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Orden de venta',
        tracking=True,
        ondelete='restrict',
    )
    purchase_order_id = fields.Many2one(
        comodel_name='purchase.order',
        string='Orden de compra',
        tracking=True,
        ondelete='restrict',
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario de pago',
        required=True,
        tracking=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
    )
    advance_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta de anticipo',
        required=True,
        tracking=True,
        domain="[('account_type', 'in', ('asset_receivable', 'asset_current', 'asset_prepayments', 'liability_payable', 'liability_current'))]",
        help='Cuenta contable de anticipo (no CxC/CxP estándar del contacto). '
             'El pago se registra en esta cuenta y se concilia al facturar.',
    )
    advance_invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Factura de anticipo (legacy)',
        readonly=True,
        copy=False,
        tracking=True,
        help='Campo legacy; los anticipos actuales no generan factura.',
    )
    payment_id = fields.Many2one(
        comodel_name='account.payment',
        string='Pago generado',
        readonly=True,
        copy=False,
        tracking=True,
    )
    amount = fields.Monetary(
        string='Monto del adelanto',
        required=True,
        currency_field='currency_id',
        tracking=True,
    )
    amount_applied = fields.Monetary(
        string='Monto aplicado',
        compute='_compute_amount_applied',
        store=True,
        currency_field='currency_id',
        tracking=True,
    )
    amount_residual = fields.Monetary(
        string='Saldo disponible',
        compute='_compute_amount_residual',
        store=True,
        currency_field='currency_id',
        tracking=True,
    )
    invoice_ids = fields.Many2many(
        comodel_name='account.move',
        relation='kenocia_advance_payment_invoice_rel',
        column1='advance_id',
        column2='invoice_id',
        string='Facturas finales aplicadas',
        copy=False,
        tracking=True,
    )
    application_ids = fields.One2many(
        comodel_name='kenocia.advance.application',
        inverse_name='advance_id',
        string='Aplicaciones',
    )
    invoice_count = fields.Integer(
        string='Facturas aplicadas',
        compute='_compute_invoice_count',
    )
    applied_invoice_count = fields.Integer(
        string='Facturas finales',
        compute='_compute_invoice_count',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('confirmed', 'Confirmado'),
            ('partially_applied', 'Aplicado Parcialmente'),
            ('fully_applied', 'Aplicado Totalmente'),
            ('cancelled', 'Cancelado'),
        ],
        string='Estado',
        default='draft',
        required=True,
        index=True,
        tracking=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda',
        required=True,
        default=lambda self: self.env.company.currency_id,
        tracking=True,
    )
    date = fields.Date(
        string='Fecha',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    notes = fields.Text(string='Notas internas', tracking=True)
    void_reason = fields.Text(string='Motivo de cancelación', tracking=True)
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )

    _LOCKED_STATES = frozenset({
        'confirmed', 'partially_applied', 'fully_applied', 'cancelled',
    })
    _WRITE_BYPASS_CONTEXT_KEY = 'kenocia_advance_bypass_lock'

    _sql_constraints = [
        (
            'positive_amount',
            'CHECK(amount > 0)',
            'El monto del adelanto debe ser mayor a cero.',
        ),
        (
            'exclusive_order',
            'CHECK(sale_order_id IS NULL OR purchase_order_id IS NULL)',
            'Un adelanto no puede vincularse a una Orden de Venta y una de Compra simultáneamente.',
        ),
    ]

    @api.depends('application_ids.amount')
    def _compute_amount_applied(self):
        for advance in self:
            advance.amount_applied = sum(advance.application_ids.mapped('amount'))

    @api.depends('amount', 'amount_applied')
    def _compute_amount_residual(self):
        for advance in self:
            advance.amount_residual = advance.amount - advance.amount_applied

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for advance in self:
            advance.invoice_count = len(advance.invoice_ids)
            advance.applied_invoice_count = len(advance.invoice_ids)

    @api.depends('name', 'partner_id', 'advance_type')
    def _compute_display_name(self):
        type_labels = dict(self._fields['advance_type'].selection)
        for advance in self:
            parts = [
                advance.name if advance.name and advance.name != '/' else False,
                advance.partner_id.display_name,
                type_labels.get(advance.advance_type),
            ]
            advance.display_name = ' — '.join(p for p in parts if p) or _('Adelanto')

    @api.model
    def _kenocia_user_can_manage_cxc(self):
        user = self.env.user
        return (
            user.has_group('kenocia_tesoreria_v18.group_tesoreria_cxc')
            or user.has_group('kenocia_tesoreria_v18.group_tesoreria_supervisor')
            or user.has_group('kenocia_tesoreria_v18.group_tesoreria_admin')
        )

    @api.model
    def _kenocia_user_can_manage_cxp(self):
        user = self.env.user
        return (
            user.has_group('kenocia_tesoreria_v18.group_tesoreria_cxp')
            or user.has_group('kenocia_tesoreria_v18.group_tesoreria_supervisor')
            or user.has_group('kenocia_tesoreria_v18.group_tesoreria_admin')
        )

    @api.model
    def _check_advance_type_role(self, advance_type):
        if not advance_type:
            return
        if advance_type == 'customer' and not self._kenocia_user_can_manage_cxc():
            raise AccessError(_(
                'No tiene permiso para crear o modificar adelantos de clientes (CXC).',
            ))
        if advance_type == 'supplier' and not self._kenocia_user_can_manage_cxp():
            raise AccessError(_(
                'No tiene permiso para crear o modificar adelantos de proveedores (CXP).',
            ))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_advance_type_role(vals.get('advance_type'))
            if not vals.get('advance_account_id') and vals.get('advance_type'):
                company = self.env['res.company'].browse(
                    vals.get('company_id'),
                ) if vals.get('company_id') else self.env.company
                if vals['advance_type'] == 'customer':
                    vals['advance_account_id'] = (
                        company.kenocia_advance_account_cxc_id.id
                    )
                else:
                    vals['advance_account_id'] = (
                        company.kenocia_advance_account_cxp_id.id
                    )
        return super().create(vals_list)

    def write(self, vals):
        if 'advance_type' in vals:
            self._check_advance_type_role(vals['advance_type'])
        if 'name' in vals and not self.env.context.get(self._WRITE_BYPASS_CONTEXT_KEY):
            raise UserError(_(
                'La referencia se genera automáticamente al confirmar el adelanto.',
            ))
        if not self.env.context.get(self._WRITE_BYPASS_CONTEXT_KEY):
            locked_records = self.filtered(
                lambda advance: advance.state in self._LOCKED_STATES,
            )
            if locked_records and vals:
                raise UserError(_(
                    'No puede modificar un adelanto confirmado o cerrado. '
                    'Use «Pasar a borrador» si necesita realizar cambios.',
                ))
        return super().write(vals)

    @api.onchange('advance_type')
    def _onchange_advance_type(self):
        self.partner_id = False
        self.sale_order_id = False
        self.purchase_order_id = False
        company = self.company_id or self.env.company
        if self.advance_type == 'customer':
            self.advance_account_id = company.kenocia_advance_account_cxc_id
        elif self.advance_type == 'supplier':
            self.advance_account_id = company.kenocia_advance_account_cxp_id

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        self.sale_order_id = False
        self.purchase_order_id = False

    @api.constrains('amount', 'sale_order_id', 'purchase_order_id', 'currency_id')
    def _check_amount_vs_order(self):
        for advance in self:
            order = advance.sale_order_id or advance.purchase_order_id
            if not order:
                continue
            order_total = (
                advance.sale_order_id.amount_total
                if advance.sale_order_id
                else advance.purchase_order_id.amount_total
            )
            if advance.currency_id != order.currency_id:
                raise ValidationError(_(
                    'La moneda del adelanto (%(adv)s) no coincide con la de la orden (%(ord)s).',
                    adv=advance.currency_id.name,
                    ord=order.currency_id.name,
                ))
            if advance.amount > order_total:
                raise ValidationError(_(
                    'El adelanto (%(adv)s) supera el total de la orden (%(ord)s).',
                    adv=advance.currency_id.format(advance.amount),
                    ord=order.currency_id.format(order_total),
                ))

    @api.constrains('advance_type', 'sale_order_id', 'purchase_order_id', 'partner_id')
    def _check_order_partner_coherence(self):
        for advance in self:
            if advance.advance_type == 'customer' and advance.purchase_order_id:
                raise ValidationError(_(
                    'Un adelanto de cliente no puede vincularse a una orden de compra.',
                ))
            if advance.advance_type == 'supplier' and advance.sale_order_id:
                raise ValidationError(_(
                    'Un adelanto de proveedor no puede vincularse a una orden de venta.',
                ))
            order = advance.sale_order_id or advance.purchase_order_id
            if order and order.partner_id.commercial_partner_id != advance.partner_id.commercial_partner_id:
                raise ValidationError(_(
                    'El contacto del adelanto debe coincidir con el de la orden vinculada.',
                ))

    def _get_sequence_code(self):
        self.ensure_one()
        return (
            'kenocia.advance.payment.cxc'
            if self.advance_type == 'customer'
            else 'kenocia.advance.payment.cxp'
        )

    def _assign_name(self):
        for advance in self:
            if advance.name and advance.name != '/':
                continue
            advance.with_context(kenocia_advance_bypass_lock=True).write({
                'name': (
                    self.env['ir.sequence'].next_by_code(advance._get_sequence_code())
                    or _('Nuevo')
                ),
            })

    @api.constrains('advance_account_id', 'advance_type')
    def _check_advance_account(self):
        for advance in self:
            if not advance.advance_account_id:
                continue
            if not advance.advance_account_id.reconcile:
                raise ValidationError(_(
                    'La cuenta de anticipo %(account)s debe tener activada '
                    '«Permitir conciliación» en el plan de cuentas.',
                    account=advance.advance_account_id.display_name,
                ))

    def _create_advance_payment(self):
        self.ensure_one()
        payment_type = 'inbound' if self.advance_type == 'customer' else 'outbound'
        partner_type = 'customer' if self.advance_type == 'customer' else 'supplier'
        payment = self.env['account.payment'].with_context(
            force_payment_move=True,
        ).create({
            'payment_type': payment_type,
            'partner_type': partner_type,
            'partner_id': self.partner_id.id,
            'amount': self.amount,
            'currency_id': self.currency_id.id,
            'journal_id': self.journal_id.id,
            'date': self.date,
            'memo': _('Anticipo %(ref)s', ref=self.name),
        })
        payment.write({'destination_account_id': self.advance_account_id.id})
        payment._kenocia_generate_and_post_move()
        if payment.state in ('draft', 'in_process'):
            payment.action_validate()
        return payment

    def _get_application_journal(self):
        self.ensure_one()
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not journal:
            raise UserError(_(
                'Configure un diario misceláneo para registrar aplicaciones de anticipo.',
            ))
        return journal

    def _prepare_application_move_line_vals(self, account, debit, credit):
        self.ensure_one()
        vals = {
            'account_id': account.id,
            'partner_id': self.partner_id.id,
            'debit': debit,
            'credit': credit,
            'name': _('Aplicación adelanto %(ref)s', ref=self.name),
        }
        if account.account_type in ('asset_receivable', 'liability_payable'):
            vals['date_maturity'] = fields.Date.context_today(self)
        return vals

    def _create_application_move(self, invoice, amount_to_apply):
        """Asiento de aplicación: anticipo → CxC/CxP de la factura final."""
        self.ensure_one()
        invoice_line = invoice.line_ids.filtered(
            lambda line: line.account_id.account_type in (
                'asset_receivable', 'liability_payable',
            ) and not line.reconciled,
        )[:1]
        if not invoice_line:
            raise UserError(_('No se encontró línea por cobrar/pagar en la factura.'))

        advance_account = self.advance_account_id
        invoice_account = invoice_line.account_id
        if self.advance_type == 'customer':
            debit_account, credit_account = advance_account, invoice_account
        else:
            debit_account, credit_account = invoice_account, advance_account

        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self._get_application_journal().id,
            'date': fields.Date.context_today(self),
            'ref': self.name,
            'line_ids': [
                (0, 0, self._prepare_application_move_line_vals(
                    debit_account, amount_to_apply, 0,
                )),
                (0, 0, self._prepare_application_move_line_vals(
                    credit_account, 0, amount_to_apply,
                )),
            ],
        })
        move.action_post()
        application_line = move.line_ids.filtered(
            lambda line: line.account_id == invoice_account and not line.reconciled,
        )[:1]
        if application_line:
            (application_line + invoice_line).reconcile()
        return move

    def _get_advance_receipt_title(self):
        self.ensure_one()
        if self.advance_type == 'customer':
            return _('Recibo de anticipo de cliente')
        return _('Recibo de anticipo de proveedor')

    def _get_advance_receipt_type_label(self):
        self.ensure_one()
        labels = dict(self._fields['advance_type'].selection)
        return labels.get(self.advance_type, '')

    def _get_advance_receipt_partner_label(self):
        self.ensure_one()
        return _('Cliente') if self.advance_type == 'customer' else _('Proveedor')

    def _get_advance_receipt_documents(self):
        """Documentos vinculados al anticipo para el recibo impreso."""
        self.ensure_one()
        documents = []
        for application in self.application_ids.sorted(
            key=lambda app: (
                app.invoice_id.invoice_date or app.invoice_id.date or '',
                app.invoice_id.name or '',
            ),
        ):
            invoice = application.invoice_id
            documents.append({
                'move': invoice,
                'date': invoice.invoice_date or invoice.date,
                'name': invoice.name,
                'ref': invoice.ref or invoice.payment_reference or '',
                'amount': application.amount,
                'currency': self.currency_id,
            })
        if documents:
            return documents

        order = self.sale_order_id or self.purchase_order_id
        if order:
            documents.append({
                'move': order,
                'date': order.date_order.date() if order.date_order else self.date,
                'name': order.name,
                'ref': _('Orden vinculada'),
                'amount': self.amount,
                'currency': self.currency_id,
            })
        return documents

    def _get_advance_receipt_standard_note(self):
        self.ensure_one()
        residual = self.currency_id.format(self.amount_residual)
        if self.advance_type == 'customer':
            return _(
                'Este documento certifica el registro de un anticipo recibido del '
                'cliente, aplicable a facturas futuras. Saldo pendiente de '
                'aplicación: %(residual)s.',
                residual=residual,
            )
        return _(
            'Este documento certifica el registro de un anticipo entregado al '
            'proveedor, aplicable a facturas futuras. Saldo pendiente de '
            'aplicación: %(residual)s.',
            residual=residual,
        )

    def _get_advance_receipt_report_values(self):
        self.ensure_one()
        payment = self.payment_id
        return {
            'display_documents': True,
            'display_payment_method': bool(payment and payment.payment_method_id),
            'receipt_documents': self._get_advance_receipt_documents(),
            'receipt_partner': self.partner_id,
            'advance_note': self.notes or '',
            'advance_standard_note': self._get_advance_receipt_standard_note(),
        }

    def action_confirm_advance(self):
        for advance in self.filtered(lambda a: a.state == 'draft'):
            if not advance.advance_account_id:
                raise UserError(_('Debe indicar la cuenta de anticipo.'))
            advance._assign_name()
            payment = advance._create_advance_payment()
            advance.with_context(
                kenocia_advance_bypass_lock=True,
            ).write({
                'payment_id': payment.id,
                'state': 'confirmed',
            })
            advance.message_post(
                body=_(
                    'Anticipo confirmado.<br/>'
                    'Pago: <b>%(payment)s</b><br/>'
                    'Cuenta: <b>%(account)s</b>',
                    payment=payment.display_name,
                    account=advance.advance_account_id.display_name,
                ),
                subtype_xmlid='mail.mt_note',
            )
            order = advance.sale_order_id or advance.purchase_order_id
            if order:
                order.message_post(
                    body=_(
                        'Anticipo <b>%(advance)s</b> confirmado por <b>%(amount)s</b>.',
                        advance=advance.name,
                        amount=advance.currency_id.format(advance.amount),
                    ),
                    subtype_xmlid='mail.mt_note',
                )
        return True

    def _apply_to_invoice(self, invoice, amount_to_apply):
        self.ensure_one()
        if self.state not in ('confirmed', 'partially_applied'):
            raise UserError(_(
                'El adelanto %(name)s está en estado %(state)s. Confírmelo primero.',
                name=self.name,
                state=dict(self._fields['state'].selection).get(self.state, self.state),
            ))
        if amount_to_apply <= 0:
            raise ValidationError(_('El monto a aplicar debe ser mayor a cero.'))
        if amount_to_apply > self.amount_residual:
            raise ValidationError(_(
                'El monto supera el saldo residual del adelanto (%(res)s).',
                res=self.currency_id.format(self.amount_residual),
            ))
        if amount_to_apply > invoice.amount_residual:
            raise ValidationError(_(
                'El monto supera el saldo de la factura (%(res)s).',
                res=invoice.currency_id.format(invoice.amount_residual),
            ))
        if self.currency_id != invoice.currency_id:
            raise ValidationError(_(
                'La moneda del adelanto (%(adv)s) no coincide con la factura (%(inv)s).',
                adv=self.currency_id.name,
                inv=invoice.currency_id.name,
            ))
        if invoice.partner_id.commercial_partner_id != self.partner_id.commercial_partner_id:
            raise ValidationError(_(
                'Solo se pueden aplicar adelantos del mismo cliente/proveedor de la factura.',
            ))
        if not self.payment_id or self.payment_id.state not in ('paid', 'in_process'):
            raise UserError(_('El anticipo no tiene un pago contable publicado.'))

        self._create_application_move(invoice, amount_to_apply)

        self.env['kenocia.advance.application'].create({
            'advance_id': self.id,
            'invoice_id': invoice.id,
            'amount': amount_to_apply,
        })
        new_applied = self.amount_applied
        new_state = 'fully_applied' if self.currency_id.compare_amounts(
            new_applied, self.amount,
        ) >= 0 else 'partially_applied'
        self.with_context(kenocia_advance_bypass_lock=True).write({
            'state': new_state,
            'invoice_ids': [(4, invoice.id)],
        })
        self.message_post(
            body=_(
                'Aplicado <b>%(amount)s</b> a la factura <b>%(invoice)s</b>. '
                'Saldo residual: <b>%(residual)s</b>.',
                amount=self.currency_id.format(amount_to_apply),
                invoice=invoice.display_name,
                residual=self.currency_id.format(self.amount_residual),
            ),
            subtype_xmlid='mail.mt_note',
        )
        invoice.message_post(
            body=_(
                'Adelanto <b>%(advance)s</b> aplicado por <b>%(amount)s</b>.',
                advance=self.name,
                amount=self.currency_id.format(amount_to_apply),
            ),
            subtype_xmlid='mail.mt_note',
        )
        return True

    def action_apply_advance_wizard(self):
        self.ensure_one()
        invoice = self.env.context.get('active_model') == 'account.move' and self.env.context.get('active_id')
        invoice = self.env['account.move'].browse(invoice) if invoice else self.env['account.move']
        if not invoice:
            raise UserError(_('Abra el asistente desde una factura publicada.'))
        return invoice.action_apply_advances()

    def action_cancel_advance(self):
        for advance in self:
            if advance.state in ('fully_applied', 'cancelled'):
                raise UserError(_('No se puede cancelar un adelanto en este estado.'))
            if advance.amount_applied > 0:
                raise UserError(_(
                    'Tiene %(amount)s aplicados en facturas. '
                    'Revierta las aplicaciones antes de cancelar.',
                    amount=advance.currency_id.format(advance.amount_applied),
                ))
            if advance.payment_id and advance.payment_id.state != 'canceled':
                advance.payment_id.action_cancel()
            if advance.advance_invoice_id and advance.advance_invoice_id.state != 'cancel':
                advance.advance_invoice_id.button_cancel()
            advance.with_context(kenocia_advance_bypass_lock=True).write({
                'state': 'cancelled',
            })
            advance.message_post(
                body=_('Adelanto cancelado.'),
                subtype_xmlid='mail.mt_note',
            )
        return True

    def action_set_to_draft(self):
        """Vuelve a borrador un adelanto confirmado sin aplicaciones."""
        for advance in self:
            if advance.state != 'confirmed':
                raise UserError(_(
                    'Solo adelantos en estado Confirmado pueden pasar a borrador.',
                ))
            if advance.amount_applied > 0 or advance.application_ids:
                raise UserError(_(
                    'No puede pasar a borrador un adelanto con montos aplicados a facturas.',
                ))
            if advance.payment_id and advance.payment_id.state != 'canceled':
                advance.payment_id.action_cancel()
            if advance.advance_invoice_id and advance.advance_invoice_id.state != 'cancel':
                advance.advance_invoice_id.button_cancel()
            advance.with_context(kenocia_advance_bypass_lock=True).write({
                'state': 'draft',
                'payment_id': False,
                'advance_invoice_id': False,
            })
            advance.message_post(
                body=_(
                    'Anticipo regresado a <b>borrador</b>. '
                    'Se canceló el pago; puede editar y confirmar nuevamente.',
                ),
                subtype_xmlid='mail.mt_note',
            )
        return True

    @api.model
    def _get_advances_to_apply_on_invoice(self, invoice):
        advance_type = (
            'customer' if invoice.move_type in ('out_invoice', 'out_refund')
            else 'supplier'
        )
        domain = [
            ('partner_id', '=', invoice.partner_id.commercial_partner_id.id),
            ('advance_type', '=', advance_type),
            ('currency_id', '=', invoice.currency_id.id),
            ('state', 'in', ('confirmed', 'partially_applied')),
            ('amount_residual', '>', 0),
        ]
        advances = self.search(domain)
        sale_orders = invoice.invoice_line_ids.mapped('sale_line_ids.order_id')
        purchase_orders = invoice.invoice_line_ids.mapped('purchase_line_id.order_id')
        if sale_orders or purchase_orders:
            order_advances = self.env['kenocia.advance.payment']
            for order in sale_orders:
                order_advances |= order.advance_payment_ids.filtered(
                    lambda adv: adv in advances,
                )
            for order in purchase_orders:
                order_advances |= order.advance_payment_ids.filtered(
                    lambda adv: adv in advances,
                )
            if order_advances:
                return order_advances
        return advances

    @api.model
    def _auto_apply_to_invoice(self, invoice):
        """Aplica automáticamente anticipos al publicar una factura manual."""
        invoice.ensure_one()
        if not invoice.is_invoice(include_receipts=True):
            return
        remaining = invoice.amount_residual
        for advance in self._get_advances_to_apply_on_invoice(invoice):
            if invoice.currency_id.is_zero(remaining):
                break
            amount = min(advance.amount_residual, remaining)
            if amount <= 0:
                continue
            advance._apply_to_invoice(invoice, amount)
            invoice.invalidate_recordset(['amount_residual'])
            remaining = invoice.amount_residual

    def action_view_payment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pago'),
            'res_model': 'account.payment',
            'view_mode': 'form',
            'res_id': self.payment_id.id,
        }

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Facturas aplicadas'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.invoice_ids.ids)],
        }

    def action_view_sale_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Orden de venta'),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
        }

    def action_view_purchase_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Orden de compra'),
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'res_id': self.purchase_order_id.id,
        }


class KenociaAdvanceApplication(models.Model):
    _name = 'kenocia.advance.application'
    _description = 'Aplicación de adelanto a factura'
    _order = 'id desc'

    advance_id = fields.Many2one(
        comodel_name='kenocia.advance.payment',
        string='Adelanto',
        required=True,
        ondelete='cascade',
        index=True,
    )
    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Factura',
        required=True,
        ondelete='restrict',
        index=True,
    )
    amount = fields.Monetary(
        string='Monto aplicado',
        required=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        related='advance_id.currency_id',
        store=True,
    )
    company_id = fields.Many2one(
        related='advance_id.company_id',
        store=True,
    )

    _sql_constraints = [
        (
            'positive_application_amount',
            'CHECK(amount > 0)',
            'El monto aplicado debe ser mayor a cero.',
        ),
    ]
