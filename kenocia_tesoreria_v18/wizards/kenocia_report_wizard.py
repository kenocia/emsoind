# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

import base64
import csv
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class KenociaReportWizard(models.TransientModel):
    _name = 'kenocia.report.wizard'
    _description = 'Wizard — Reportes de Tesorería'

    report_type = fields.Selection(
        selection=[
            ('payments', 'Operaciones de Tesorería'),
            ('advances', 'Adelantos CXC/CXP'),
        ],
        string='Tipo de reporte',
        required=True,
        default='payments',
    )
    date_from = fields.Date(
        string='Desde',
        required=True,
        default=fields.Date.context_today,
    )
    date_to = fields.Date(
        string='Hasta',
        required=True,
        default=fields.Date.context_today,
    )
    journal_ids = fields.Many2many(
        comodel_name='account.journal',
        string='Diarios',
        domain="[('type', 'in', ('bank', 'cash'))]",
    )
    advance_type = fields.Selection(
        selection=[
            ('all', 'Todos'),
            ('customer', 'Clientes (CXC)'),
            ('supplier', 'Proveedores (CXP)'),
        ],
        string='Tipo de adelanto',
        default='all',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_to < wizard.date_from:
                raise UserError(_('La fecha "Hasta" debe ser mayor o igual a "Desde".'))

    def _get_payment_domain(self):
        self.ensure_one()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('tesoreria_type', '!=', False),
            ('state', 'not in', ('canceled', 'rejected')),
        ]
        if self.journal_ids:
            domain.append(('journal_id', 'in', self.journal_ids.ids))
        return domain

    def _get_advance_domain(self):
        self.ensure_one()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('state', '!=', 'cancelled'),
        ]
        if self.advance_type != 'all':
            domain.append(('advance_type', '=', self.advance_type))
        if self.journal_ids:
            domain.append(('journal_id', 'in', self.journal_ids.ids))
        return domain

    def action_print_pdf(self):
        self.ensure_one()
        if self.report_type == 'payments':
            records = self.env['account.payment'].search(
                self._get_payment_domain(),
                order='date desc, id desc',
            )
            if not records:
                raise UserError(_('No hay operaciones de tesorería en el rango seleccionado.'))
            report = self.env.ref('kenocia_tesoreria_v18.action_report_kenocia_tesoreria')
            return report.with_context(
                report_date_from=self.date_from,
                report_date_to=self.date_to,
            ).report_action(records, config=False)
        advances = self.env['kenocia.advance.payment'].search(
            self._get_advance_domain(),
            order='date desc, id desc',
        )
        if not advances:
            raise UserError(_('No hay adelantos en el rango seleccionado.'))
        report = self.env.ref('kenocia_tesoreria_v18.action_report_kenocia_advance_receipt')
        return report.with_context(
            report_date_from=self.date_from,
            report_date_to=self.date_to,
        ).report_action(advances, config=False)

    def action_export_csv(self):
        self.ensure_one()
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        filename = 'tesoreria_report.csv'

        if self.report_type == 'payments':
            records = self.env['account.payment'].search(
                self._get_payment_domain(),
                order='date desc, id desc',
            )
            if not records:
                raise UserError(_('No hay operaciones de tesorería en el rango seleccionado.'))
            writer.writerow([
                'Fecha', 'Número', 'Tipo Tesorería', 'Contacto', 'Diario',
                'Monto', 'Estado', 'Conciliado', 'Secuencia',
            ])
            type_labels = dict(
                self.env['account.payment']._fields['tesoreria_type'].selection
            )
            state_labels = dict(
                self.env['account.payment']._fields['state'].selection
            )
            for payment in records:
                writer.writerow([
                    payment.date,
                    payment.name or '',
                    type_labels.get(payment.tesoreria_type, ''),
                    payment.partner_id.display_name,
                    payment.journal_id.display_name,
                    payment.amount,
                    state_labels.get(payment.state, ''),
                    'Sí' if payment.is_reconciled else 'No',
                    payment.kenocia_sequence_name or '',
                ])
            filename = 'tesoreria_operaciones.csv'
        else:
            records = self.env['kenocia.advance.payment'].search(
                self._get_advance_domain(),
                order='date desc, id desc',
            )
            if not records:
                raise UserError(_('No hay adelantos en el rango seleccionado.'))
            writer.writerow([
                'Referencia', 'Fecha', 'Tipo', 'Contacto', 'Diario',
                'Monto', 'Aplicado', 'Saldo', 'Estado',
            ])
            type_labels = dict(
                self.env['kenocia.advance.payment']._fields['advance_type'].selection
            )
            state_labels = dict(
                self.env['kenocia.advance.payment']._fields['state'].selection
            )
            for advance in records:
                writer.writerow([
                    advance.name,
                    advance.date,
                    type_labels.get(advance.advance_type, ''),
                    advance.partner_id.display_name,
                    advance.journal_id.display_name,
                    advance.amount,
                    advance.amount_applied,
                    advance.amount_residual,
                    state_labels.get(advance.state, ''),
                ])
            filename = 'tesoreria_adelantos.csv'

        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(
                output.getvalue().encode('utf-8-sig'),
            ),
            'mimetype': 'text/csv',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }
