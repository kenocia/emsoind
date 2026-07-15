# -*- coding: utf-8 -*-
"""Nacionalización de productos bajo régimen de Zona Libre (ZOLI).

Cuando una empresa ZOLI vende en el mercado local hondureño, el producto se
nacionaliza (importación definitiva) y debe pagar DAI (Derechos Arancelarios a
la Importación) + ISV sobre el valor de los componentes importados.

Motor de cálculo del DAI:
  - Producto NO originario (TLC): DAI = Valor del producto terminado × % DAI
    del producto (tasa SAC).
  - Producto SÍ originario (TLC): el bien final entra con 0% de arancel; el DAI
    se aplica únicamente sobre los insumos no originarios (de terceros países)
    consumidos para fabricarlo:
        DAI = Σ (Valor del insumo no originario × % DAI de ese insumo)
ISV de nacionalización = (Base DAI + DAI) × 15%.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMoveZoli(models.Model):
    _inherit = 'account.move'

    tipo_operacion_zoli = fields.Selection([
        ('exportacion', 'Exportación'),
        ('nacionalizacion', 'Nacionalización (venta local)'),
    ], string='Tipo de Operación ZOLI',
       compute='_compute_tipo_operacion_zoli',
       store=True,
       readonly=False,
       copy=False,
       help='Clasificación de la venta para empresas de Zona Libre. La '
            'nacionalización (venta local) genera tributos DAI + ISV. Se '
            'propone desde la Orden de Venta y es editable.')

    es_zoli = fields.Boolean(
        related='company_id.es_zoli',
        string='Compañía ZOLI',
    )

    zoli_base_dai = fields.Monetary(
        string='Base DAI (Nacionalización)',
        compute='_compute_zoli_nacionalizacion',
        store=True,
        currency_field='currency_id',
        help='Base imponible para el cálculo del DAI: valor del producto '
             'terminado (no originario) o valor de insumos no originarios '
             '(originario).',
    )
    zoli_dai_amount = fields.Monetary(
        string='DAI a pagar',
        compute='_compute_zoli_nacionalizacion',
        store=True,
        currency_field='currency_id',
    )
    zoli_isv_nacionalizacion = fields.Monetary(
        string='ISV Nacionalización',
        compute='_compute_zoli_nacionalizacion',
        store=True,
        currency_field='currency_id',
    )
    zoli_total_tributos = fields.Monetary(
        string='Total Tributos Nacionalización',
        compute='_compute_zoli_nacionalizacion',
        store=True,
        currency_field='currency_id',
    )
    zoli_calculo_html = fields.Html(
        string='Detalle de Nacionalización',
        compute='_compute_zoli_nacionalizacion',
        store=True,
        sanitize=False,
    )

    @api.depends('sale_order_id', 'sale_order_id.tipo_operacion_zoli',
                 'company_id.es_zoli')
    def _compute_tipo_operacion_zoli(self):
        for move in self:
            if not move.company_id.es_zoli:
                move.tipo_operacion_zoli = False
            elif move.sale_order_id.tipo_operacion_zoli:
                move.tipo_operacion_zoli = move.sale_order_id.tipo_operacion_zoli
            else:
                move.tipo_operacion_zoli = move.tipo_operacion_zoli or False

    def _zoli_sale_orders(self):
        """Órdenes de venta vinculadas a la factura."""
        self.ensure_one()
        orders = self.sale_order_id
        if 'sale_line_ids' in self.env['account.move.line']._fields:
            orders |= self.invoice_line_ids.sale_line_ids.order_id
        return orders

    def _zoli_valor_insumos_no_originarios(self):
        """Suma DAI y base de insumos no originarios consumidos (CMP).

        Requiere kc_manual_production (modelo kc.production.consumption). Si no
        está disponible, devuelve ceros y lo indica en el detalle.
        """
        self.ensure_one()
        base = dai = 0.0
        detalle = []
        if 'kc.production.consumption' not in self.env:
            return base, dai, detalle, False
        orders = self._zoli_sale_orders()
        if not orders:
            return base, dai, detalle, True
        consumos = self.env['kc.production.consumption'].search([
            ('sale_order_id', 'in', orders.ids),
            ('state', '=', 'done'),
            ('company_id', '=', self.company_id.id),
        ])
        for cmp_line in consumos.mapped('line_ids'):
            product = cmp_line.product_id
            if cmp_line.line_type != 'material':
                continue
            if not (product.requiere_control_duca and product.es_no_originario):
                continue
            valor = cmp_line.qty * product.standard_price
            pct = product.porcentaje_dai_insumo or 0.0
            linea_dai = valor * pct / 100.0
            base += valor
            dai += linea_dai
            detalle.append((product.display_name, cmp_line.qty, valor, pct, linea_dai))
        return base, dai, detalle, True

    @api.depends('tipo_operacion_zoli', 'company_id.es_zoli', 'state',
                 'invoice_line_ids.price_subtotal', 'invoice_line_ids.product_id',
                 'move_type', 'currency_id')
    def _compute_zoli_nacionalizacion(self):
        for move in self:
            move.zoli_base_dai = 0.0
            move.zoli_dai_amount = 0.0
            move.zoli_isv_nacionalizacion = 0.0
            move.zoli_total_tributos = 0.0
            move.zoli_calculo_html = ''
            if (not move.company_id.es_zoli
                    or move.tipo_operacion_zoli != 'nacionalizacion'
                    or move.move_type not in ('out_invoice', 'out_refund')):
                continue

            filas = []
            base_dai = dai = 0.0

            for line in move._fiscal_invoice_lines(move):
                product = line.product_id
                if not product:
                    continue
                if not product.es_originario_tlc:
                    pct = product.porcentaje_dai or 0.0
                    valor = line.price_subtotal
                    linea_dai = valor * pct / 100.0
                    base_dai += valor
                    dai += linea_dai
                    filas.append(
                        f'<tr><td>{product.display_name} '
                        f'<span class="badge bg-secondary">No originario</span></td>'
                        f'<td class="text-end">{valor:,.2f}</td>'
                        f'<td class="text-end">{pct:.1f}%</td>'
                        f'<td class="text-end">{linea_dai:,.2f}</td></tr>'
                    )

            # Parte originaria: DAI sobre insumos no originarios consumidos.
            tiene_originario = any(
                l.product_id.es_originario_tlc
                for l in move._fiscal_invoice_lines(move) if l.product_id
            )
            if tiene_originario:
                base_ins, dai_ins, detalle, disponible = (
                    move._zoli_valor_insumos_no_originarios())
                base_dai += base_ins
                dai += dai_ins
                if not disponible:
                    filas.append(
                        '<tr><td colspan="4" class="text-warning">Hay productos '
                        'originarios (TLC): instale/registre el Consumo de '
                        'Materia Prima (CMP) para calcular el DAI de insumos no '
                        'originarios.</td></tr>'
                    )
                for nombre, qty, valor, pct, linea_dai in detalle:
                    filas.append(
                        f'<tr><td>{nombre} '
                        f'<span class="badge bg-info">Insumo no originario</span> '
                        f'(x{qty:g})</td>'
                        f'<td class="text-end">{valor:,.2f}</td>'
                        f'<td class="text-end">{pct:.1f}%</td>'
                        f'<td class="text-end">{linea_dai:,.2f}</td></tr>'
                    )

            isv = (base_dai + dai) * 0.15
            move.zoli_base_dai = move._round_sar(base_dai)
            move.zoli_dai_amount = move._round_sar(dai)
            move.zoli_isv_nacionalizacion = move._round_sar(isv)
            move.zoli_total_tributos = move._round_sar(dai + isv)

            simbolo = move.currency_id.symbol or 'L'
            move.zoli_calculo_html = (
                '<table class="table table-sm table-bordered mb-0">'
                '<thead class="table-light"><tr>'
                '<th>Concepto</th><th class="text-end">Base</th>'
                '<th class="text-end">% DAI</th><th class="text-end">DAI</th>'
                '</tr></thead><tbody>'
                + ''.join(filas) +
                f'</tbody><tfoot class="table-dark fw-bold">'
                f'<tr><td>Totales</td>'
                f'<td class="text-end">{simbolo} {move.zoli_base_dai:,.2f}</td>'
                f'<td></td>'
                f'<td class="text-end">{simbolo} {move.zoli_dai_amount:,.2f}</td>'
                f'</tr>'
                f'<tr><td colspan="3">ISV Nacionalización (15%)</td>'
                f'<td class="text-end">{simbolo} '
                f'{move.zoli_isv_nacionalizacion:,.2f}</td></tr>'
                f'<tr><td colspan="3">TOTAL TRIBUTOS</td>'
                f'<td class="text-end">{simbolo} '
                f'{move.zoli_total_tributos:,.2f}</td></tr>'
                f'</tfoot></table>'
            )

    def _zoli_cerrar_duca(self):
        """Registra la cantidad nacionalizada en los lotes DUCA consumidos."""
        self.ensure_one()
        if 'kc.production.consumption' not in self.env:
            return
        orders = self._zoli_sale_orders()
        if not orders:
            return
        consumos = self.env['kc.production.consumption'].search([
            ('sale_order_id', 'in', orders.ids),
            ('state', '=', 'done'),
            ('company_id', '=', self.company_id.id),
        ])
        for cmp_line in consumos.mapped('line_ids'):
            lot = cmp_line.lot_id
            if not lot or not lot.es_duca:
                continue
            lot.duca_cantidad_nacionalizada += cmp_line.qty
            lot.message_post(body=_(
                'Nacionalización registrada por la factura %(factura)s: '
                '%(qty)s unidades salen del régimen de Zona Libre.',
                factura=self.name,
                qty=cmp_line.qty,
            ))

    def action_post(self):
        res = super().action_post()
        for move in self:
            if (move.company_id.es_zoli
                    and move.tipo_operacion_zoli == 'nacionalizacion'
                    and move.move_type == 'out_invoice'):
                move._zoli_cerrar_duca()
        return res
