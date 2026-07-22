# -*- coding: utf-8 -*-

from odoo import _, api, Command, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import clean_context


class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    kc_advance_id = fields.Many2one(
        'kc.expense.advance',
        string='Anticipo Vinculado',
        domain="[('employee_id', '=', employee_id), ('state', '=', 'delivered')]",
        check_company=True,
        tracking=True,
    )
    kc_fund_applied = fields.Boolean(
        compute='_compute_kc_fund_applied',
        string='Fondo aplicado',
        store=True,
    )
    kc_has_fiscal_expense = fields.Boolean(
        compute='_compute_kc_has_fiscal_expense',
        string='Tiene gasto fiscal',
    )

    @api.depends('expense_line_ids.kc_fund_move_id', 'expense_line_ids.kc_fund_move_id.state')
    def _compute_kc_fund_applied(self):
        for sheet in self:
            fund_moves = sheet.expense_line_ids.mapped('kc_fund_move_id')
            sheet.kc_fund_applied = bool(
                fund_moves and all(move.state == 'posted' for move in fund_moves),
            )

    @api.depends(
        'expense_line_ids.kc_document_number',
        'expense_line_ids.kc_document_type',
    )
    def _compute_kc_has_fiscal_expense(self):
        for sheet in self:
            sheet.kc_has_fiscal_expense = sheet._kc_has_fiscal_expenses()

    def _kc_has_fiscal_expenses(self):
        self.ensure_one()
        return any(expense._kc_is_fiscal_expense() for expense in self.expense_line_ids)

    def _kc_is_company_fiscal(self):
        self.ensure_one()
        return (
            self.payment_mode == 'company_account'
            and self._kc_has_fiscal_expenses()
        )

    @api.depends('employee_journal_id', 'payment_method_line_id', 'payment_mode',
                 'expense_line_ids.kc_document_number', 'expense_line_ids.kc_document_type')
    def _compute_journal_id(self):
        super()._compute_journal_id()
        for sheet in self:
            if sheet._kc_is_company_fiscal():
                sheet.journal_id = (
                    sheet.employee_journal_id
                    or sheet.company_id.expense_journal_id
                    or sheet.journal_id
                )

    @api.depends('account_move_ids.payment_state', 'account_move_ids.amount_residual')
    def _compute_from_account_move_ids(self):
        fiscal_company = self.filtered(lambda sheet: sheet._kc_is_company_fiscal())
        others = self - fiscal_company
        if others:
            super(HrExpenseSheet, others)._compute_from_account_move_ids()
        for sheet in fiscal_company:
            posted = sheet.account_move_ids.filtered(lambda move: move.state == 'posted')
            if posted:
                sheet.amount_residual = sum(posted.mapped('amount_residual'))
                payment_states = set(posted.mapped('payment_state'))
                if len(payment_states) == 1:
                    sheet.payment_state = payment_states.pop()
                elif 'partial' in payment_states or (
                    'paid' in payment_states and 'not_paid' in payment_states
                ):
                    sheet.payment_state = 'partial'
                elif 'paid' in payment_states:
                    sheet.payment_state = 'paid'
                else:
                    sheet.payment_state = 'not_paid'
            else:
                sheet.amount_residual = 0.0
                sheet.payment_state = 'not_paid'

    def _kc_validate_expense_sheet_fiscal_rules(self):
        for sheet in self:
            for expense in sheet.expense_line_ids:
                if expense._kc_is_fiscal_expense() and not expense.vendor_id:
                    raise UserError(_(
                        'El gasto "%(expense)s" tiene documento fiscal pero no '
                        'tiene proveedor configurado.',
                        expense=expense.name,
                    ))
            if (
                sheet.payment_mode == 'company_account'
                and sheet.kc_advance_id
                and sheet._kc_has_fiscal_expenses()
            ):
                raise UserError(_(
                    'Un gasto pagado por la empresa (tarjeta/banco) no puede '
                    'vincularse a un anticipo. Use "Empleado pagó (reembolso)" '
                    'para liquidar anticipos.',
                ))

    def _kc_get_purchase_journal(self):
        self.ensure_one()
        return (
            self.employee_journal_id
            or self.company_id.expense_journal_id
            or self.journal_id
        )

    def _prepare_bills_vals_for_expense(self, expense):
        """Una factura de proveedor por línea de gasto."""
        self.ensure_one()
        if not expense.vendor_id:
            raise UserError(_(
                'Configure el proveedor en el gasto "%s" antes de contabilizar.',
                expense.name,
            ))
        vendor = expense.vendor_id
        move_vals = self._prepare_move_vals()
        # Facturas de compra siempre usan fecha de factura (también en modo empresa).
        move_vals.pop('date', None)
        invoice_date = (
            expense.kc_document_date
            or expense.date
            or self.accounting_date
            or fields.Date.context_today(self)
        )
        return {
            **move_vals,
            'journal_id': self._kc_get_purchase_journal().id,
            'ref': expense.name or self.name,
            'move_type': 'in_invoice',
            'partner_id': vendor.id,
            'commercial_partner_id': vendor.commercial_partner_id.id,
            'currency_id': expense.currency_id.id or self.currency_id.id,
            'company_id': self.company_id.id,
            'invoice_date': invoice_date,
            'line_ids': [Command.create(expense._prepare_move_lines_vals())],
            'attachment_ids': [
                Command.create(
                    attachment.copy_data({
                        'res_model': 'account.move',
                        'res_id': False,
                        'raw': attachment.raw,
                    })[0],
                )
                for attachment in expense.attachment_ids
            ],
            **expense._kc_fiscal_header_vals(),
        }

    def _kc_create_vendor_bills_for_sheets(self):
        """Crea una factura proveedor por línea (reembolso o empresa fiscal)."""
        moves_sudo = self.env['account.move']
        for sheet in self:
            sheet.accounting_date = (
                sheet.accounting_date or sheet._calculate_default_accounting_date()
            )
            for expense in sheet.expense_line_ids:
                move_vals = sheet._prepare_bills_vals_for_expense(expense)
                move_sudo = self.env['account.move'].sudo().create(move_vals)
                expense.sudo().write({'kc_vendor_bill_id': move_sudo.id})
                if move_sudo.attachment_ids:
                    move_sudo._message_set_main_attachment_id(
                        move_sudo.attachment_ids,
                        force=True,
                        filter_xml=False,
                    )
                moves_sudo |= move_sudo
        return moves_sudo

    def _do_create_moves(self):
        self._kc_validate_expense_sheet_fiscal_rules()
        own_account_sheets = self.filtered(
            lambda sheet: sheet.payment_mode == 'own_account',
        )
        company_fiscal_sheets = self.filtered(
            lambda sheet: sheet._kc_is_company_fiscal(),
        )
        company_other_sheets = self.filtered(
            lambda sheet: (
                sheet.payment_mode == 'company_account'
                and not sheet._kc_has_fiscal_expenses()
            ),
        )

        self = self.with_context(clean_context(self.env.context))
        moves_sudo = self.env['account.move']

        vendor_bill_sheets = own_account_sheets | company_fiscal_sheets
        if vendor_bill_sheets:
            moves_sudo |= vendor_bill_sheets._kc_create_vendor_bills_for_sheets()

        if company_other_sheets:
            moves_sudo |= super(
                HrExpenseSheet, company_other_sheets,
            )._do_create_moves()

        return moves_sudo.sudo(self.env.su)

    def _do_reverse_moves(self):
        for sheet in self:
            expenses = sheet.expense_line_ids
            fund_moves = expenses.mapped('kc_fund_move_id')
            posted_funds = fund_moves.filtered(lambda move: move.state == 'posted')
            if posted_funds:
                posted_funds._reverse_moves(
                    default_values_list=[
                        {'ref': False} for _move in posted_funds
                    ],
                    cancel=True,
                )
            fund_moves.filtered(lambda move: move.state == 'draft').unlink()
            expenses.write({
                'kc_fund_move_id': False,
                'kc_vendor_bill_id': False,
            })
        return super()._do_reverse_moves()

    def _kc_get_fund_journal(self):
        self.ensure_one()
        company = self.company_id
        if company.kc_expense_fund_journal_id:
            return company.kc_expense_fund_journal_id
        journal = self.env['account.journal'].search([
            ('company_id', '=', company.id),
            ('type', '=', 'general'),
        ], limit=1)
        return journal or self.journal_id

    def _kc_get_reimbursement_account(self):
        self.ensure_one()
        company = self.company_id
        if company.kc_expense_reimbursement_account_id:
            return company.kc_expense_reimbursement_account_id
        partner = self.employee_id.sudo().work_contact_id
        if not partner:
            raise UserError(_(
                'El empleado %s no tiene contacto de trabajo configurado.',
                self.employee_id.name,
            ))
        partner = partner.with_company(company)
        account = (
            partner.property_account_payable_id
            or partner.parent_id.property_account_payable_id
        )
        if not account:
            raise UserError(_(
                'Configure la cuenta por pagar del empleado %s o la cuenta de '
                'reembolso en la compañía.',
                self.employee_id.name,
            ))
        return account

    def _kc_get_employee_partner(self):
        self.ensure_one()
        partner = self.employee_id.sudo().work_contact_id
        if not partner:
            raise UserError(_(
                'El empleado %s no tiene contacto de trabajo configurado.',
                self.employee_id.name,
            ))
        return partner

    def _kc_prepare_fund_credit_commands(self, amount, employee_partner):
        """Líneas de crédito: anticipo disponible y/o reembolso empleado."""
        self.ensure_one()
        credit_lines = []
        remaining = amount
        advance = self.kc_advance_id

        if advance and remaining:
            available = advance._get_advance_available_balance()
            from_advance = min(available, remaining)
            if from_advance:
                credit_lines.append(Command.create({
                    'account_id': advance.account_advance_id.id,
                    'partner_id': employee_partner.id,
                    'debit': 0.0,
                    'credit': from_advance,
                    'name': _('Aplicación anticipo — %s', self.employee_id.name),
                }))
                remaining -= from_advance

        if remaining:
            reimb_account = self._kc_get_reimbursement_account()
            credit_lines.append(Command.create({
                'account_id': reimb_account.id,
                'partner_id': employee_partner.id,
                'debit': 0.0,
                'credit': remaining,
                'name': _('Reembolso empleado — %s', self.employee_id.name),
            }))
        return credit_lines

    def _kc_create_fund_clearing_move(self, invoice, expense):
        """Cancela CxP proveedor contra anticipo o reembolso del empleado."""
        self.ensure_one()
        if expense.kc_fund_move_id:
            return expense.kc_fund_move_id

        payable_lines = invoice.line_ids.filtered(
            lambda line: line.account_id.account_type == 'liability_payable'
            and not line.reconciled
            and line.credit > 0,
        )
        if not payable_lines:
            raise UserError(_(
                'La factura %(invoice)s no tiene línea por pagar para aplicar '
                'el fondo del empleado.',
                invoice=invoice.display_name,
            ))

        payable_account = payable_lines[0].account_id
        vendor = expense.vendor_id
        amount = invoice.amount_total
        employee_partner = self._kc_get_employee_partner()
        journal = self._kc_get_fund_journal()

        credit_commands = self._kc_prepare_fund_credit_commands(
            amount, employee_partner,
        )
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': invoice.invoice_date or fields.Date.context_today(self),
            'ref': _('Aplicación fondo — %(expense)s', expense=expense.name),
            'expense_sheet_id': self.id,
            'line_ids': [
                Command.create({
                    'account_id': payable_account.id,
                    'partner_id': vendor.id,
                    'debit': amount,
                    'credit': 0.0,
                    'name': _('Pago a proveedor vía empleado — %s', vendor.name),
                }),
                *credit_commands,
            ],
        })
        move.action_post()
        expense.kc_fund_move_id = move.id

        lines_to_reconcile = payable_lines + move.line_ids.filtered(
            lambda line: line.account_id == payable_account
            and line.partner_id == vendor
            and line.debit > 0
            and not line.reconciled,
        )
        lines_to_reconcile.reconcile()

        if self.kc_advance_id:
            advance_account = self.kc_advance_id.account_advance_id
            advance_lines = self.env['account.move.line'].search([
                ('account_id', '=', advance_account.id),
                ('partner_id', '=', employee_partner.id),
                ('reconciled', '=', False),
                ('parent_state', '=', 'posted'),
            ])
            if advance_lines:
                advance_lines.reconcile()

        return move

    def _kc_apply_fund_to_vendor_bills(self):
        for sheet in self.filtered(lambda rec: rec.payment_mode == 'own_account'):
            for expense in sheet.expense_line_ids:
                invoice = expense.kc_vendor_bill_id
                if not invoice or invoice.state != 'posted':
                    continue
                if expense.kc_fund_move_id:
                    continue
                sheet._kc_create_fund_clearing_move(invoice, expense)

    def action_sheet_move_post(self):
        fiscal_company = self.filtered(lambda sheet: sheet._kc_is_company_fiscal())
        others = self - fiscal_company

        if fiscal_company:
            fiscal_company.filtered(
                lambda sheet: not sheet.account_move_ids,
            )._do_create_moves()
            fiscal_company.account_move_ids.action_post()

        res = True
        if others:
            res = super(HrExpenseSheet, others).action_sheet_move_post()

        self._kc_apply_fund_to_vendor_bills()
        return res

    def action_open_account_moves(self):
        self.ensure_one()
        if self._kc_is_company_fiscal() or self.payment_mode == 'own_account':
            res_model = 'account.move'
            record_ids = self.account_move_ids
            action = {'type': 'ir.actions.act_window', 'res_model': res_model}
            if len(record_ids) == 1:
                action.update({
                    'name': record_ids.name,
                    'view_mode': 'form',
                    'res_id': record_ids.id,
                    'views': [(False, 'form')],
                })
            else:
                action.update({
                    'name': _('Facturas de proveedor'),
                    'view_mode': 'list',
                    'domain': [('id', 'in', record_ids.ids)],
                    'views': [(False, 'list'), (False, 'form')],
                })
            return action
        return super().action_open_account_moves()

    def action_register_payment(self):
        for sheet in self:
            if sheet.payment_mode == 'own_account' and sheet._kc_has_fiscal_expenses():
                raise UserError(_(
                    'Las facturas de proveedor de este reporte se pagan '
                    'automáticamente contra el anticipo o la cuenta de reembolso '
                    'del empleado. Para reembolsar al empleado use tesorería '
                    'sobre su cuenta por pagar (contacto del empleado).',
                ))
            if sheet._kc_is_company_fiscal():
                raise UserError(_(
                    'Este reporte generó facturas de proveedor pendientes. '
                    'Páguelas desde Contabilidad → Facturas de proveedor '
                    '(partner del comercio), o concilie con el estado de cuenta '
                    'de la tarjeta/banco corporativo.',
                ))
            if sheet.kc_advance_id:
                raise UserError(_(
                    'Este reporte está vinculado al anticipo "%(advance)s". '
                    'Las facturas se aplican al fondo automáticamente.',
                    advance=sheet.kc_advance_id.display_name,
                ))
        return super().action_register_payment()
