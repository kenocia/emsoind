# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class KcExpenseAdvance(models.Model):
    _name = 'kc.expense.advance'
    _description = 'Anticipo a Empleado para Gastos'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_delivered desc, id desc'

    OPEN_STATES = ('delivered', 'pending_settlement')

    name = fields.Char(
        string='Referencia',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('Nuevo'),
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Empleado',
        required=True,
        tracking=True,
        check_company=True,
    )
    date_delivered = fields.Date(
        string='Fecha de Entrega',
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    amount = fields.Monetary(
        string='Monto Anticipo',
        required=True,
        tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        required=True,
        index=True,
    )

    account_advance_id = fields.Many2one(
        'account.account',
        string='Cuenta Anticipo por Liquidar',
        required=True,
        check_company=True,
        domain="[('reconcile', '=', True), ('deprecated', '=', False)]",
        help='Cuenta conciliable. Debe quedar en cero al liquidar por completo.',
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario de Entrega',
        domain="[('type', 'in', ['bank', 'cash'])]",
        required=True,
        check_company=True,
    )

    expense_sheet_ids = fields.One2many(
        'hr.expense.sheet',
        'kc_advance_id',
        string='Reportes de Gastos Vinculados',
    )
    expense_sheet_count = fields.Integer(
        compute='_compute_expense_sheet_count',
    )
    vendor_bill_count = fields.Integer(
        compute='_compute_vendor_bill_count',
    )

    delivery_move_id = fields.Many2one(
        'account.move',
        string='Asiento de Entrega',
        readonly=True,
        copy=False,
    )
    closing_move_id = fields.Many2one(
        'account.move',
        string='Asiento de Cierre',
        readonly=True,
        copy=False,
    )

    amount_spent = fields.Monetary(
        compute='_compute_amounts',
        string='Total Gastado',
        store=True,
        currency_field='currency_id',
    )
    amount_balance = fields.Monetary(
        compute='_compute_amounts',
        string='Saldo Pendiente',
        store=True,
        currency_field='currency_id',
    )

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('delivered', 'Entregado'),
        ('pending_settlement', 'Pendiente de liquidación'),
        ('closed', 'Cerrado'),
    ], default='draft', tracking=True, required=True)

    @api.depends('expense_sheet_ids')
    def _compute_expense_sheet_count(self):
        for advance in self:
            advance.expense_sheet_count = len(advance.expense_sheet_ids)

    @api.depends(
        'expense_sheet_ids.expense_line_ids.kc_vendor_bill_id',
    )
    def _compute_vendor_bill_count(self):
        for advance in self:
            bills = advance.expense_sheet_ids.expense_line_ids.mapped(
                'kc_vendor_bill_id',
            )
            advance.vendor_bill_count = len(bills)

    @api.depends(
        'amount',
        'expense_sheet_ids.expense_line_ids.kc_fund_move_id',
        'expense_sheet_ids.expense_line_ids.kc_fund_move_id.state',
        'expense_sheet_ids.expense_line_ids.kc_fund_move_id.line_ids',
        'account_advance_id',
        'employee_id',
    )
    def _compute_amounts(self):
        for rec in self:
            applied = 0.0
            employee_partner = rec.employee_id.sudo().work_contact_id
            for sheet in rec.expense_sheet_ids:
                for expense in sheet.expense_line_ids:
                    move = expense.kc_fund_move_id
                    if not move or move.state != 'posted':
                        continue
                    for line in move.line_ids:
                        if (
                            line.account_id == rec.account_advance_id
                            and line.partner_id == employee_partner
                            and line.credit > 0
                        ):
                            applied += line.credit
            rec.amount_spent = applied
            rec.amount_balance = rec.amount - applied

    def _get_advance_available_balance(self):
        """Saldo del anticipo aún aplicable (líneas abiertas en cuenta anticipo)."""
        self.ensure_one()
        partner = self._get_employee_partner()
        lines = self.env['account.move.line'].search([
            ('account_id', '=', self.account_advance_id.id),
            ('partner_id', '=', partner.id),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
        ])
        return sum(lines.mapped('debit')) - sum(lines.mapped('credit'))

    @api.model
    def _advance_open_domain(self, employee, company, exclude_id=False):
        domain = [
            ('employee_id', '=', employee.id),
            ('company_id', '=', company.id),
            ('state', 'in', list(self.OPEN_STATES)),
        ]
        if exclude_id:
            domain.append(('id', '!=', exclude_id))
        return domain

    @api.constrains('employee_id', 'state', 'company_id')
    def _check_single_open_advance(self):
        for advance in self:
            if advance.state not in self.OPEN_STATES:
                continue
            duplicate = self.search(
                advance._advance_open_domain(
                    advance.employee_id,
                    advance.company_id,
                    exclude_id=advance.id,
                ),
                limit=1,
            )
            if duplicate:
                raise ValidationError(_(
                    'El empleado %(employee)s ya tiene un anticipo sin liquidar: '
                    '%(advance)s (estado: %(state)s).\n'
                    'Debe cerrar o liquidar ese anticipo antes de abrir otro.',
                    employee=advance.employee_id.name,
                    advance=duplicate.name,
                    state=dict(self._fields['state'].selection).get(duplicate.state),
                ))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'kc.expense.advance',
                ) or _('Nuevo')
        records = super().create(vals_list)
        for advance in records.filtered(lambda rec: rec.state in self.OPEN_STATES):
            advance._check_single_open_advance()
        return records

    def _get_employee_partner(self):
        self.ensure_one()
        partner = self.employee_id.sudo().work_contact_id
        if not partner:
            raise UserError(_(
                'El empleado %s no tiene contacto de trabajo configurado.',
                self.employee_id.name,
            ))
        return partner

    def _get_employee_payable_account(self):
        self.ensure_one()
        partner = self._get_employee_partner().with_company(self.company_id)
        account = (
            partner.property_account_payable_id
            or partner.parent_id.property_account_payable_id
        )
        if not account:
            raise UserError(_(
                'Configure la cuenta por pagar del empleado %s antes de '
                'liquidar un faltante.',
                self.employee_id.name,
            ))
        return account

    def action_deliver(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Solo se puede entregar un anticipo en borrador.'))
        duplicate = self.search(
            self._advance_open_domain(self.employee_id, self.company_id, self.id),
            limit=1,
        )
        if duplicate:
            raise UserError(_(
                'No puede entregar este anticipo. El empleado %(employee)s ya '
                'tiene el anticipo %(advance)s sin liquidar.',
                employee=self.employee_id.name,
                advance=duplicate.name,
            ))
        if not self.journal_id.default_account_id:
            raise UserError(_(
                'Configure la cuenta por defecto del diario %s.',
                self.journal_id.display_name,
            ))

        partner = self._get_employee_partner()
        move = self.env['account.move'].create({
            'journal_id': self.journal_id.id,
            'date': self.date_delivered,
            'ref': _('Anticipo a %(employee)s — %(ref)s',
                     employee=self.employee_id.name, ref=self.name),
            'line_ids': [
                (0, 0, {
                    'account_id': self.account_advance_id.id,
                    'partner_id': partner.id,
                    'debit': self.amount,
                    'credit': 0.0,
                    'name': _('Anticipo gastos — %s', self.employee_id.name),
                }),
                (0, 0, {
                    'account_id': self.journal_id.default_account_id.id,
                    'debit': 0.0,
                    'credit': self.amount,
                    'name': _('Entrega anticipo — %s', self.employee_id.name),
                }),
            ],
        })
        move.action_post()
        self.write({
            'delivery_move_id': move.id,
            'state': 'delivered',
        })
        self.message_post(body=_(
            'Anticipo entregado: %(amount)s a %(employee)s',
            amount=self.amount,
            employee=self.employee_id.name,
        ))

    def action_close(self):
        """Siempre solicita confirmación antes de liquidar."""
        self.ensure_one()
        if self.state not in ('delivered', 'pending_settlement'):
            raise UserError(_(
                'Solo se puede liquidar un anticipo en estado Entregado o '
                'Pendiente de liquidación.',
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Confirmar liquidación de anticipo'),
            'res_model': 'kc.expense.advance.close.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_advance_id': self.id,
                'default_amount_balance': self.amount_balance,
            },
        }

    def action_confirm_manual_settlement(self):
        """Cierra un anticipo con faltante tras el pago/cuadre manual en contabilidad."""
        self.ensure_one()
        if self.state != 'pending_settlement':
            raise UserError(_(
                'Esta acción solo aplica a anticipos pendientes de liquidación.',
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Confirmar liquidación manual'),
            'res_model': 'kc.expense.advance.close.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_advance_id': self.id,
                'default_amount_balance': self.amount_balance,
            },
        }

    def action_view_expense_sheets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reportes de Gastos'),
            'res_model': 'hr.expense.sheet',
            'view_mode': 'list,form',
            'domain': [('kc_advance_id', '=', self.id)],
        }

    def action_view_vendor_bills(self):
        self.ensure_one()
        bills = self.expense_sheet_ids.expense_line_ids.mapped('kc_vendor_bill_id')
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Facturas Proveedor'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', bills.ids)],
            'context': {'default_move_type': 'in_invoice'},
        }
        if len(bills) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': bills.id,
            })
        return action

    def action_view_advance_account_moves(self):
        self.ensure_one()
        partner = self._get_employee_partner()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Apuntes — Cuenta Anticipo'),
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': [
                ('account_id', '=', self.account_advance_id.id),
                ('partner_id', '=', partner.id),
            ],
        }
