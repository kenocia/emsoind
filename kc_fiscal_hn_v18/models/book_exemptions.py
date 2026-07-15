# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .fiscal_book_mixin import BOOK_ESTADO
from .fiscal_period import (
    action_notify_and_open_list,
    check_fiscal_period,
    numero_factura_ventas,
)


class BookExemptions(models.Model):
    """Libro de Exoneraciones SAR."""

    _name = 'kc_fiscal_hn.book.exemptions'
    _description = 'Libro de Exoneraciones SAR'
    _inherit = ['kc.fiscal.book.mixin', 'mail.thread', 'mail.activity.mixin']
    _order = 'fecha desc, numero_factura'

    numero_factura = fields.Char(string='N° Factura', index=True, tracking=True)
    rtn_cliente = fields.Char(string='RTN Cliente', tracking=True)
    cliente = fields.Char(string='Cliente', required=True, tracking=True)
    numero_constancia_exonerado = fields.Char(
        string='N° constancia exonerado', tracking=True,
    )
    numero_oc_exenta = fields.Char(string='N° OC exenta', tracking=True)
    monto_exonerado = fields.Monetary(
        string='Monto exonerado', currency_field='currency_id', tracking=True,
    )
    total_factura = fields.Monetary(
        string='Total factura', currency_field='currency_id', tracking=True,
    )

    @api.depends('numero_factura', 'cliente')
    def _compute_display_name(self) -> None:
        for line in self:
            line.display_name = f'{line.numero_factura or ""} — {line.cliente or ""}'

    @api.model
    def _tiene_monto_exonerado(self, move):
        return bool(move.amount_exonerado or move.exonerado)

    @api.model
    def _prepare_from_move(self, move, date_from, date_to) -> dict | None:
        if not self._tiene_monto_exonerado(move):
            return None
        numero = numero_factura_ventas(move)
        if not numero:
            return None
        monto = move.amount_exonerado
        if not monto and move.exonerado:
            monto = move.amount_exento
        if not monto:
            return None
        return {
            'company_id': move.company_id.id,
            'move_id': move.id,
            'fecha': move.invoice_date or move.date,
            'numero_factura': numero,
            'rtn_cliente': move.commercial_partner_id.vat or '',
            'cliente': move.commercial_partner_id.name or '',
            'numero_constancia_exonerado': move.noConsRegistroExonerado or '',
            'numero_oc_exenta': move.noOrdenCompraExenta or '',
            'monto_exonerado': monto,
            'total_factura': move.amount_total,
            'periodo_desde': date_from,
            'periodo_hasta': date_to,
            'estado': 'pendiente',
        }

    @api.model
    def _period_domain(self, company, date_from, date_to):
        return [
            ('company_id', '=', company.id),
            ('periodo_desde', '=', date_from),
            ('periodo_hasta', '=', date_to),
        ]

    @api.model
    def action_generar_desde_facturas(self, date_from, date_to, company_id=None, replace=False):
        check_fiscal_period(date_from, date_to)
        company = self.env['res.company'].browse(company_id) if company_id else self.env.company
        period_domain = self._period_domain(company, date_from, date_to)
        if replace:
            self.with_context(skip_book_line_lock=True).search(
                period_domain,
            ).unlink()

        moves = self.env['account.move'].search([
            ('company_id', '=', company.id),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
            ('journal_id.type', '=', 'sale'),
            '|', ('amount_exonerado', '>', 0), ('exonerado', '=', True),
        ])
        existing = set(self.search(period_domain).mapped('move_id').ids)
        vals_list = []
        sin_numero = 0
        for move in moves:
            if move.id in existing:
                continue
            vals = self._prepare_from_move(move, date_from, date_to)
            if vals:
                vals_list.append(vals)
            else:
                sin_numero += 1

        created = self.with_context(skip_book_line_lock=True).create(
            vals_list,
        ) if vals_list else self.browse()

        if not created:
            ventas_periodo = self.env['account.move'].search_count([
                ('company_id', '=', company.id),
                ('move_type', 'in', ('out_invoice', 'out_refund')),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', date_from),
                ('invoice_date', '<=', date_to),
            ])
            if ventas_periodo:
                if moves:
                    raise UserError(_(
                        'No se generaron líneas de exoneraciones.\n\n'
                        'Hay %(n)s factura(s) marcada(s) como exonerada(s), '
                        'pero %(sin_num)s no tienen numeración fiscal válida.\n\n'
                        'Confirme las facturas con correlativo SAR y complete '
                        'N° constancia / N° OC exenta en la pestaña SAR.',
                        n=len(moves),
                        sin_num=sin_numero,
                    ))
                raise UserError(_(
                    'No hay facturas exoneradas en el período.\n\n'
                    'El libro de exoneraciones solo incluye ventas con '
                    'monto exonerado o marcadas como exoneradas en SAR.',
                ))

        return action_notify_and_open_list(
            self.env,
            self._name,
            period_domain,
            _('Libro de Exoneraciones'),
            _('Se generaron %s líneas.', len(created)),
            list_name=_('Libro de Exoneraciones SAR'),
        )

    def action_exportar_excel(self):
        if not self:
            raise UserError(_('No hay líneas para exportar.'))
        headers = [
            'Fecha', 'N° Factura', 'RTN', 'Cliente', 'N° constancia', 'N° OC exenta',
            'Monto exonerado', 'Total factura', 'Estado', 'Fecha declaración',
            'Declarado por', 'Notas',
        ]
        estado_labels = dict(BOOK_ESTADO)
        rows = [
            [
                str(l.fecha or ''), l.numero_factura or '', l.rtn_cliente or '', l.cliente or '',
                l.numero_constancia_exonerado or '', l.numero_oc_exenta or '',
                l.monto_exonerado, l.total_factura,
                estado_labels.get(l.estado, ''), str(l.fecha_declaracion or ''),
                l.declarado_por.name or '', l.notas_rectificacion or '',
            ]
            for l in self
        ]
        return self._export_book_excel('Libro_Exoneraciones_SAR', headers, rows)
