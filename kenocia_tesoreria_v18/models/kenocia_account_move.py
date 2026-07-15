# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv.expression import OR
from odoo.tools.safe_eval import safe_eval


class AccountMove(models.Model):
    _inherit = 'account.move'

    advance_payment_ids = fields.Many2many(
        comodel_name='kenocia.advance.payment',
        relation='kenocia_advance_payment_invoice_rel',
        column1='invoice_id',
        column2='advance_id',
        string='Adelantos aplicados',
        copy=False,
        tracking=True,
    )
    advance_count = fields.Integer(
        string='Adelantos aplicados',
        compute='_compute_advance_counts',
    )
    advance_available_count = fields.Integer(
        string='Adelantos disponibles',
        compute='_compute_advance_counts',
    )
    total_advance_applied = fields.Monetary(
        string='Total adelantos aplicados',
        compute='_compute_advance_amounts',
        store=True,
        currency_field='currency_id',
    )
    residual_after_advance = fields.Monetary(
        string='Saldo después de adelantos',
        compute='_compute_advance_amounts',
        store=True,
        currency_field='currency_id',
    )

    @api.depends(
        'advance_payment_ids',
        'partner_id',
        'state',
        'move_type',
    )
    def _compute_advance_counts(self):
        for move in self:
            move.advance_count = len(move.advance_payment_ids)
            if move.state == 'posted' and move.is_invoice(include_receipts=True):
                move.advance_available_count = len(move._get_applicable_advances())
            else:
                move.advance_available_count = 0

    @api.depends(
        'advance_payment_ids.application_ids.amount',
        'advance_payment_ids.application_ids.invoice_id',
        'amount_residual',
        'currency_id',
    )
    def _compute_advance_amounts(self):
        for move in self:
            applications = move.advance_payment_ids.application_ids.filtered(
                lambda app: app.invoice_id == move,
            )
            move.total_advance_applied = sum(applications.mapped('amount'))
            move.residual_after_advance = move.amount_residual

    def action_post(self):
        posted_invoices = self.filtered(
            lambda move: move.is_invoice(include_receipts=True),
        )
        res = super().action_post()
        if not self.env.context.get('kenocia_skip_auto_apply_advance'):
            for invoice in posted_invoices.filtered(lambda m: m.state == 'posted'):
                self.env['kenocia.advance.payment']._auto_apply_to_invoice(invoice)
        return res

    def _get_applicable_advances(self):
        self.ensure_one()
        return self.env['kenocia.advance.payment']._get_advances_to_apply_on_invoice(
            self,
        )

    def action_apply_advances(self):
        self.ensure_one()
        if self.state != 'posted':
            raise UserError(_('Solo puede aplicar adelantos a facturas publicadas.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Aplicar Adelantos'),
            'res_model': 'kenocia.apply.advance.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_invoice_id': self.id},
        }

    def action_view_advances(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Adelantos aplicados'),
            'res_model': 'kenocia.advance.payment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.advance_payment_ids.ids)],
            'context': {'create': False},
        }

    def _kenocia_is_petty_cash_fiscal_bill(self):
        """Factura de compra registrada en diario fiscal SAR (FA o Boleta)."""
        self.ensure_one()
        return (
            self.move_type == 'in_invoice'
            and self.state == 'posted'
            and self.journal_id.document_fiscal in ('vendors', 'boleta')
        )

    def _kenocia_get_petty_cash_fiscal_errors(self):
        """
        Validaciones fiscales SAR para liquidar caja chica con factura de proveedor.

        Reglas según tipo de contribuyente de la empresa (kc_fiscal_hn_v18):
        - Pequeño: diario FA/Boleta + correlativo del proveedor.
        - Mediano/Grande (obligado DMC): RTN proveedor HN, CAI, correlativo,
          fecha emisión, clase documento SAR y montos SAR.
        """
        self.ensure_one()
        errors = []
        company = self.company_id
        partner = self.partner_id
        doc_fiscal = self.journal_id.document_fiscal or ''

        if self.move_type != 'in_invoice':
            errors.append(_('Solo se pueden liquidar facturas de proveedor (BILL).'))
            return errors

        if doc_fiscal not in ('vendors', 'boleta'):
            errors.append(_(
                'La factura debe registrarse en un diario fiscal de compras '
                '«Factura Proveedor (FA)» o «Boleta de Compra» '
                '(Configuración → Diarios contables → Documento Fiscal).'
            ))
            return errors

        is_hn_vendor = (
            partner.country_id
            and partner.country_id.code == 'HN'
        )

        if doc_fiscal == 'vendors' and is_hn_vendor:
            if not self.correlativo_proveedor:
                errors.append(_(
                    'Falta el N° correlativo del proveedor '
                    '(pestaña SAR de la factura).'
                ))
            if not self.cai_proveedor:
                errors.append(_(
                    'Falta el CAI del proveedor (pestaña SAR de la factura).'
                ))
            if not self.femision_proveedor:
                errors.append(_(
                    'Falta la fecha de emisión del proveedor '
                    '(pestaña SAR de la factura).'
                ))

        if doc_fiscal == 'boleta' and is_hn_vendor and not self.correlativo_proveedor:
            errors.append(_(
                'Falta el número del comprobante / boleta del proveedor '
                '(pestaña SAR).'
            ))

        if is_hn_vendor and company.obligado_dmc and not partner.vat:
            errors.append(_(
                'El proveedor «%(vendor)s» no tiene RTN. '
                'Es obligatorio para respaldar crédito fiscal en la DMC.',
                vendor=partner.display_name,
            ))
        elif is_hn_vendor and partner.is_company and not partner.vat:
            errors.append(_(
                'El proveedor empresa «%(vendor)s» no tiene RTN registrado.',
                vendor=partner.display_name,
            ))

        if company.obligado_dmc and doc_fiscal == 'vendors':
            if is_hn_vendor and not self.class_document_sar:
                errors.append(_(
                    'Clasifique el documento SAR como FA u OC '
                    '(pestaña SAR / DMC de la factura).'
                ))
            if not self.montos_sar:
                errors.append(_(
                    'Indique Montos SAR: al costo, al gasto, importación '
                    'o no deducible.'
                ))

        if self.fiscal_validation_status == 'error' and self.fiscal_validation_message:
            errors.append(_(
                'Validación fiscal con error: %(msg)s',
                msg=self.fiscal_validation_message,
            ))

        return errors


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    kenocia_is_advance_account = fields.Boolean(
        string='Cuenta de anticipo Kenocia',
        compute='_compute_kenocia_is_advance_account',
        search='_search_kenocia_is_advance_account',
    )

    @api.model
    def _kenocia_get_advance_account_ids(self, company=None):
        company = company or self.env.company
        return list(filter(None, [
            company.kenocia_advance_account_cxc_id.id,
            company.kenocia_advance_account_cxp_id.id,
        ]))

    @api.model
    def _kenocia_get_treasury_account_ids(self, company=None):
        company = company or self.env.company
        account_ids = self._kenocia_get_advance_account_ids(company)
        journals = self.env['account.journal'].search([
            ('type', 'in', ('bank', 'cash')),
            ('company_id', '=', company.id),
        ])
        account_ids.extend(journals.mapped('default_account_id').ids)
        return list(set(filter(None, account_ids)))

    @api.depends('account_id')
    def _compute_kenocia_is_advance_account(self):
        advance_ids = set(self._kenocia_get_advance_account_ids())
        for line in self:
            line.kenocia_is_advance_account = line.account_id.id in advance_ids

    @api.model
    def _search_kenocia_is_advance_account(self, operator, value):
        if operator != '=':
            return []
        advance_ids = self._kenocia_get_advance_account_ids()
        if not advance_ids:
            return [('id', '=', False)] if value else []
        if value:
            return [('account_id', 'in', advance_ids)]
        return [('account_id', 'not in', advance_ids)]

    @api.model
    def action_kenocia_open_reconcile(self):
        treasury_account_ids = self._kenocia_get_treasury_account_ids()
        account_conditions = [
            [('account_id.account_type', '=', 'asset_receivable')],
            [('account_id.account_type', '=', 'liability_payable')],
        ]
        if treasury_account_ids:
            account_conditions.append([('account_id', 'in', treasury_account_ids)])
        domain = [
            ('display_type', 'not in', ('line_section', 'line_note')),
            ('account_id.reconcile', '=', True),
            ('full_reconcile_id', '=', False),
        ] + OR(account_conditions)

        action = self.env['ir.actions.actions']._for_xml_id(
            'account_accountant.action_move_line_posted_unreconciled',
        )
        action_context = action.get('context') or {}
        if isinstance(action_context, str):
            action_context = safe_eval(action_context)
        action['name'] = _('Conciliación manual')
        action['domain'] = domain
        action['context'] = {
            **action_context,
            'search_default_posted_lines': 1,
            'search_default_unreconciled': 1,
            'search_default_group_by_account': 1,
            'search_default_group_by_partner': 1,
        }
        return action
