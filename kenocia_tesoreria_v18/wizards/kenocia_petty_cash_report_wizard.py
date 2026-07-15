# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

import base64
import csv
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class KenociaPettyCashReportWizard(models.TransientModel):
    _name = 'kenocia.petty.cash.report.wizard'
    _description = 'Wizard — Reportes Caja Chica'

    report_type = fields.Selection(
        selection=[
            ('operational', 'Reporte operativo'),
            ('fiscal', 'Reporte fiscal SAR'),
        ],
        string='Tipo de reporte',
        required=True,
        default='operational',
    )
    fund_ids = fields.Many2many(
        comodel_name='kenocia.petty.cash',
        string='Fondos',
        help='Dejar vacío para incluir todos los fondos.',
    )
    date_from = fields.Date(
        string='Fecha desde',
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string='Fecha hasta',
        required=True,
        default=fields.Date.context_today,
    )
    custodian_ids = fields.Many2many(
        comodel_name='res.partner',
        string='Custodios',
        help='Dejar vacío para incluir todos los custodios.',
    )
    state_filter = fields.Selection(
        selection=[
            ('all', 'Todos los estados'),
            ('open', 'Solo fondos abiertos'),
            ('closed', 'Solo fondos cerrados'),
        ],
        string='Estado del fondo',
        default='all',
    )
    output_format = fields.Selection(
        selection=[
            ('pdf', 'PDF'),
            ('csv', 'CSV'),
        ],
        string='Formato',
        default='pdf',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_to < wizard.date_from:
                raise UserError(_('La fecha "Hasta" debe ser mayor o igual a "Desde".'))

    def _get_fund_domain(self):
        self.ensure_one()
        domain = [('company_id', '=', self.company_id.id)]
        if self.fund_ids:
            domain.append(('id', 'in', self.fund_ids.ids))
        if self.custodian_ids:
            domain.append(('custodian_id', 'in', self.custodian_ids.ids))
        if self.state_filter != 'all':
            domain.append(('state', '=', self.state_filter))
        return domain

    def _get_report_data(self):
        """Dataset para reporte operativo."""
        self.ensure_one()
        funds = self.env['kenocia.petty.cash'].search(
            self._get_fund_domain(),
            order='name',
        )
        line_state_labels = dict(
            self.env['kenocia.petty.cash.line']._fields['state'].selection,
        )
        recharge_state_labels = dict(
            self.env['kenocia.petty.cash.recharge']._fields['state'].selection,
        )
        fund_state_labels = dict(
            self.env['kenocia.petty.cash']._fields['state'].selection,
        )

        result = []
        for fund in funds:
            advances = fund.line_ids.filtered(
                lambda line: (
                    line.date
                    and self.date_from <= line.date <= self.date_to
                    and line.state != 'cancelled'
                ),
            )
            recharges = fund.recharge_ids.filtered(
                lambda recharge: (
                    recharge.date
                    and self.date_from <= recharge.date <= self.date_to
                    and recharge.state != 'cancelled'
                ),
            )
            result.append({
                'fund': fund,
                'fund_state_label': fund_state_labels.get(fund.state, fund.state),
                'advances': advances,
                'recharges': recharges,
                'total_recharges': sum(
                    recharge.amount for recharge in recharges
                    if recharge.state == 'received'
                ),
                'total_delivered': sum(advances.mapped('amount')),
                'total_settled': sum(
                    line.amount for line in advances if line.state == 'settled'
                ),
                'total_pending': sum(
                    line.amount for line in advances if line.state == 'delivered'
                ),
                'total_returned': sum(advances.mapped('amount_returned')),
                'line_state_labels': line_state_labels,
                'recharge_state_labels': recharge_state_labels,
            })

        if not result:
            raise UserError(_('No hay fondos con movimientos en el período seleccionado.'))

        return {
            'funds': result,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company': self.company_id,
            'currency': self.company_id.currency_id,
            'total_global_delivered': sum(item['total_delivered'] for item in result),
            'total_global_settled': sum(item['total_settled'] for item in result),
            'total_global_pending': sum(item['total_pending'] for item in result),
            'total_global_recharges': sum(item['total_recharges'] for item in result),
        }

    def _get_fiscal_data(self):
        """Dataset para reporte fiscal SAR (solo anticipos liquidados)."""
        self.ensure_one()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'settled'),
            ('invoice_id', '!=', False),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        if self.fund_ids:
            domain.append(('petty_cash_id', 'in', self.fund_ids.ids))
        if self.custodian_ids:
            domain.append(('petty_cash_id.custodian_id', 'in', self.custodian_ids.ids))
        if self.state_filter != 'all':
            domain.append(('petty_cash_id.state', '=', self.state_filter))

        advances = self.env['kenocia.petty.cash.line'].search(
            domain,
            order='date, id',
        )

        rows = []
        for adv in advances:
            inv = adv.invoice_id
            rows.append({
                'fecha': adv.date,
                'fondo': adv.petty_cash_id.name,
                'custodio': adv.petty_cash_id.custodian_id.display_name,
                'empleado': adv.employee_id.display_name,
                'concepto': adv.description,
                'proveedor': inv.partner_id.display_name,
                'rtn': inv.partner_id.vat or '',
                'cai': inv.cai_proveedor or '',
                'correlativo': inv.correlativo_proveedor or '',
                'fecha_emision': inv.femision_proveedor or '',
                'clase_sar': inv.class_document_sar or '',
                'base_imponible': inv.amount_untaxed,
                'isv': inv.amount_tax,
                'total_factura': inv.amount_total,
                'anticipo': adv.amount,
                'vuelto': adv.amount_returned,
            })

        if not rows:
            raise UserError(_(
                'No hay anticipos liquidados con factura SAR en el período seleccionado.',
            ))

        return {
            'rows': rows,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company': self.company_id,
            'currency': self.company_id.currency_id,
            'total_base': sum(row['base_imponible'] for row in rows),
            'total_isv': sum(row['isv'] for row in rows),
            'total_facturado': sum(row['total_factura'] for row in rows),
            'total_anticipos': sum(row['anticipo'] for row in rows),
            'count': len(rows),
        }

    def action_print_report(self):
        self.ensure_one()
        if self.report_type == 'fiscal':
            data = self._get_fiscal_data()
            if self.output_format == 'pdf':
                return self.env.ref(
                    'kenocia_tesoreria_v18.action_report_petty_cash_fiscal',
                ).report_action(self.ids, data={'report_data': data})
            return self._export_fiscal_csv(data)

        data = self._get_report_data()
        if self.output_format == 'pdf':
            return self.env.ref(
                'kenocia_tesoreria_v18.action_report_petty_cash_operational',
            ).report_action(self.ids, data={'report_data': data})
        return self._export_operational_csv(data)

    def _export_operational_csv(self, data):
        self.ensure_one()
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        writer.writerow([
            'Fondo', 'Custodio', 'Estado fondo', 'Tipo movimiento', 'Fecha',
            'Referencia', 'Empleado/Concepto', 'Monto', 'Estado', 'Factura',
            'Vuelto',
        ])
        for fund_data in data['funds']:
            fund = fund_data['fund']
            for recharge in fund_data['recharges']:
                writer.writerow([
                    fund.name,
                    fund.custodian_id.display_name,
                    fund_data['fund_state_label'],
                    'Recarga',
                    recharge.date,
                    recharge.name,
                    recharge.journal_source_id.display_name,
                    recharge.amount,
                    fund_data['recharge_state_labels'].get(recharge.state, recharge.state),
                    recharge.reference or '',
                    '',
                ])
            for line in fund_data['advances']:
                writer.writerow([
                    fund.name,
                    fund.custodian_id.display_name,
                    fund_data['fund_state_label'],
                    'Anticipo',
                    line.date,
                    line.description,
                    line.employee_id.display_name,
                    line.amount,
                    fund_data['line_state_labels'].get(line.state, line.state),
                    line.amount_invoice,
                    line.amount_returned,
                ])

        writer.writerow([])
        writer.writerow([
            'TOTALES GLOBALES', '', '', '', '', '', '',
            data['total_global_delivered'], '', data['total_global_settled'],
            data['total_global_pending'],
        ])
        return self._csv_download(output, 'caja_chica_operativo.csv')

    def _export_fiscal_csv(self, data):
        self.ensure_one()
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        writer.writerow([
            'Fecha', 'Fondo', 'Custodio', 'Empleado', 'Concepto', 'Proveedor',
            'RTN', 'CAI', 'Correlativo', 'Fecha emisión', 'Clase SAR',
            'Base imponible', 'ISV', 'Total factura', 'Anticipo', 'Vuelto',
        ])
        for row in data['rows']:
            writer.writerow([
                row['fecha'],
                row['fondo'],
                row['custodio'],
                row['empleado'],
                row['concepto'],
                row['proveedor'],
                row['rtn'],
                row['cai'],
                row['correlativo'],
                row['fecha_emision'],
                row['clase_sar'],
                row['base_imponible'],
                row['isv'],
                row['total_factura'],
                row['anticipo'],
                row['vuelto'],
            ])
        writer.writerow([])
        writer.writerow([
            'TOTALES', '', '', '', '', '', '', '', '', '', '',
            data['total_base'], data['total_isv'], data['total_facturado'],
            data['total_anticipos'], '',
        ])
        return self._csv_download(output, 'caja_chica_fiscal_sar.csv')

    def _csv_download(self, output, filename):
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(output.getvalue().encode('utf-8-sig')),
            'mimetype': 'text/csv',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }
