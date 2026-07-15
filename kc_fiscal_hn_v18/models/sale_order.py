# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import formatLang

from .number_utilities import NumberUtilities

_logger = logging.getLogger(__name__)
_num_util = NumberUtilities()


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    es_zoli = fields.Boolean(related='company_id.es_zoli', string='Compañía ZOLI')
    tipo_operacion_zoli = fields.Selection([
        ('exportacion', 'Exportación'),
        ('nacionalizacion', 'Nacionalización (venta local)'),
    ], string='Tipo de Operación ZOLI',
       help='Clasificación de la venta para empresas de Zona Libre:\n'
            'EXPORTACIÓN: venta al exterior, sin tributos.\n'
            'NACIONALIZACIÓN: venta en el mercado local (importación '
            'definitiva), sujeta a DAI + ISV.')

    @api.onchange('partner_id')
    def _onchange_partner_tipo_operacion_zoli(self):
        """Sugiere el tipo de operación según el país del cliente (ZOLI)."""
        if not self.company_id.es_zoli or self.tipo_operacion_zoli:
            return
        country = self.partner_id.country_id
        if country and country.code == 'HN':
            self.tipo_operacion_zoli = 'nacionalizacion'
        elif country:
            self.tipo_operacion_zoli = 'exportacion'

    def _check_cancel_restrictions(self):
        """
        Verifica que el pedido puede cancelarse.
        Bloquea si tiene facturas o entregas confirmadas.
        """
        for order in self:
            posted_invoices = order.invoice_ids.filtered(
                lambda inv: inv.state == 'posted'
            )
            if posted_invoices:
                invoice_names = ', '.join(posted_invoices.mapped('name'))
                raise UserError(_(
                    'No puede cancelar el pedido %(order)s.\n\n'
                    'Tiene %(count)d factura(s) confirmada(s):\n'
                    '%(invoices)s\n\n'
                    'Para cancelar el pedido debe primero:\n'
                    '1. Emitir una Nota de Crédito por cada '
                    'factura confirmada.\n'
                    '2. Cancelar o revertir las facturas.\n'
                    '3. Luego cancelar el pedido.',
                    order=order.name,
                    count=len(posted_invoices),
                    invoices=invoice_names,
                ))

            done_pickings = order.picking_ids.filtered(
                lambda p: p.state == 'done'
            )
            if done_pickings:
                picking_names = ', '.join(done_pickings.mapped('name'))
                raise UserError(_(
                    'No puede cancelar el pedido %(order)s.\n\n'
                    'Tiene %(count)d entrega(s) completada(s):\n'
                    '%(pickings)s\n\n'
                    'No se puede cancelar un pedido con '
                    'movimientos de inventario confirmados.\n'
                    'Contacte al administrador si necesita '
                    'procesar una devolución.',
                    order=order.name,
                    count=len(done_pickings),
                    pickings=picking_names,
                ))

    def action_cancel(self):
        """Override de cancelación con validaciones de integridad."""
        self._check_cancel_restrictions()
        return super().action_cancel()

    def _check_categorias_productos_validadas(self):
        """Bloquea confirmar la OV con productos de categoría no validada.

        Reutiliza la validación de ``product.template`` (estado distinto de
        'ok'): exige configuración contable mínima y validación de Contabilidad.
        """
        errores = []
        for order in self:
            productos = order.order_line.filtered(
                lambda line: not line.display_type and line.product_id
            ).mapped('product_id.product_tmpl_id')
            for producto in productos:
                error = producto._fiscal_categoria_validacion_error()
                if error:
                    errores.append(error)
        if errores:
            raise ValidationError(
                _("No se puede confirmar la orden de venta.\n\n")
                + "\n\n".join(dict.fromkeys(errores))
            )

    def action_confirm(self):
        """Override de confirmación con bloqueo de monto Consumidor Final."""
        self._check_categorias_productos_validadas()
        for order in self:
            order.company_id.check_consumidor_final_limit(
                order.partner_id, order.amount_total,
                order.currency_id, order,
            )
        return super().action_confirm()

    @api.model
    def _split_printable_report_pages(
        self, line_list, recordset, first_cap=14, middle_cap=30, last_cap=18, single_cap=10,
    ):
        """Parte líneas de reporte PDF según cupo por tipo de página.

        :param first_cap: página 1 (encabezado grande).
        :param middle_cap: páginas siguientes / última sin sobrecarga de totales.
        :param last_cap: umbral cómodo para página final con totales.
        :param single_cap: una sola página (header + líneas + totales).
        """
        n = len(line_list)
        empty = recordset.browse()
        if not n:
            return [empty]

        def _browse(chunk):
            return recordset.browse([line.id for line in chunk])

        if n <= single_cap:
            return [_browse(line_list)]

        pages = []
        idx = 0
        is_first = True
        while idx < n:
            rem = n - idx
            if is_first:
                if rem <= first_cap:
                    pages.append(_browse(line_list[idx:]))
                    break
                take = first_cap
                is_first = False
            else:
                # Continuación: si cabe en una hoja (con o sin totales), no abrir otra.
                if rem <= middle_cap:
                    pages.append(_browse(line_list[idx:]))
                    break
                take = middle_cap
            pages.append(_browse(line_list[idx:idx + take]))
            idx += take
        return pages

    def _get_sale_quotation_report_pages(self):
        """Parte líneas imprimibles de cotización/OV.

        Página 1 lleva el encabezado completo (menor cupo); las siguientes solo
        tabla (mayor cupo). Evita el cupo fijo 26 que desbordaba la 1.ª hoja.
        Las secciones (display_type=line_section) no se imprimen.
        """
        self.ensure_one()
        lines = self._get_order_lines_to_report().filtered(
            lambda l: l.display_type != 'line_section'
        )
        return self._split_printable_report_pages(
            list(lines),
            lines,
            first_cap=14,
            middle_cap=30,
            last_cap=18,
            single_cap=10,
        )

    def _get_sale_quotation_tax_rows(self):
        """Filas de impuestos para el bloque de totales del reporte comercial."""
        self.ensure_one()
        tax_groups = {}
        for line in self.order_line.filtered(
            lambda l: not l.display_type and not l.is_downpayment
        ):
            for tax in line.tax_id:
                key = tax.id
                if key not in tax_groups:
                    tax_groups[key] = {
                        'label': self._get_sale_line_tax_label(tax),
                        'amount': 0.0,
                    }
                tax_groups[key]['amount'] += line.price_tax
        return list(tax_groups.values())

    @api.model
    def _get_sale_line_tax_label(self, tax):
        if tax.amount_type == 'percent':
            amt = tax.amount
            if amt == int(amt):
                return _('ISV %d%%') % int(amt)
            return _('ISV %.2f%%') % amt
        return tax.name

    def _sale_quotation_show_delivered_column(self):
        self.ensure_one()
        return self.state not in ('draft', 'sent')

    def _sale_quotation_format_amount(self, amount):
        """Moneda con 2 decimales en PDF (independiente de Product Price global)."""
        self.ensure_one()
        return formatLang(
            self.env, amount, digits=2, currency_obj=self.currency_id,
        )

    @api.model
    def _sale_quotation_line_code_name(self, line):
        """Separa código de producto y descripción para el PDF comercial."""
        code = ''
        if line.product_id and line.product_id.default_code:
            code = line.product_id.default_code.strip()
        name = (line.name or '').strip()
        if name.startswith('['):
            end = name.find(']')
            if end > 1:
                bracket_code = name[1:end].strip()
                if not code:
                    code = bracket_code
                name = name[end + 1:]
        # Sin líneas vacías ni saltos dobles
        parts = [part.strip() for part in name.splitlines() if part.strip()]
        first = parts[0] if parts else ''
        detail = '\n'.join(parts[1:]) if len(parts) > 1 else ''
        if code and first:
            headline = '[%s] %s' % (code, first)
        elif code:
            headline = '[%s]' % code
        else:
            headline = first or (line.name or '')
        return {
            'code': code,
            'name': '\n'.join(parts),
            'first': first,
            'headline': headline,
            'detail': detail,
        }

    # ── Factura Proforma (OV confirmada, sin datos fiscales CAI) ─────────

    proforma_amount_discount = fields.Monetary(
        string='Descuento proforma',
        compute='_compute_proforma_fiscal_totals',
        currency_field='currency_id',
    )
    proforma_amount_exento = fields.Monetary(
        string='Importe exento proforma',
        compute='_compute_proforma_fiscal_totals',
        currency_field='currency_id',
    )
    proforma_amount_exonerado = fields.Monetary(
        string='Importe exonerado proforma',
        compute='_compute_proforma_fiscal_totals',
        currency_field='currency_id',
    )
    proforma_gravado_isv15 = fields.Monetary(
        string='Gravado 15% proforma',
        compute='_compute_proforma_fiscal_totals',
        currency_field='currency_id',
    )
    proforma_gravado_isv18 = fields.Monetary(
        string='Gravado 18% proforma',
        compute='_compute_proforma_fiscal_totals',
        currency_field='currency_id',
    )
    proforma_amount_isv15 = fields.Monetary(
        string='ISV 15% proforma',
        compute='_compute_proforma_fiscal_totals',
        currency_field='currency_id',
    )
    proforma_amount_isv18 = fields.Monetary(
        string='ISV 18% proforma',
        compute='_compute_proforma_fiscal_totals',
        currency_field='currency_id',
    )
    proforma_amount_words = fields.Char(
        string='Monto en letras proforma',
        compute='_compute_proforma_fiscal_totals',
    )

    def _check_proforma_report_allowed(self):
        """Solo OV confirmadas sin factura fiscal publicada."""
        for order in self:
            if order.state not in ('sale', 'done'):
                raise UserError(_(
                    'La Factura Proforma solo está disponible para '
                    'órdenes de venta confirmadas (%(order)s).',
                    order=order.name,
                ))
            posted_invoices = order.invoice_ids.filtered(
                lambda inv: inv.state == 'posted'
                and inv.move_type == 'out_invoice'
            )
            if posted_invoices:
                names = ', '.join(posted_invoices.mapped('name'))
                raise UserError(_(
                    'No se puede imprimir la Factura Proforma de %(order)s '
                    'porque ya existe factura fiscal publicada:\n%(invoices)s',
                    order=order.name,
                    invoices=names,
                ))

    def _proforma_product_lines(self):
        self.ensure_one()
        return self.order_line.filtered(
            lambda line: not line.display_type and not line.is_downpayment
        )

    @staticmethod
    def _proforma_tax_group_lower(tax):
        return (tax.tax_group_id.name or '').strip().lower()

    def _proforma_line_is_exempt(self, line):
        if not line.tax_id:
            return True
        if any(t.tipo_impuesto == 'exento' for t in line.tax_id):
            return True
        return any(
            'exento' in self._proforma_tax_group_lower(t) for t in line.tax_id
        )

    def _proforma_line_is_exonerated(self, line):
        if not line.tax_id:
            return False
        if any(t.tipo_impuesto == 'exonerado' for t in line.tax_id):
            return True
        return any(
            'exonerado' in self._proforma_tax_group_lower(t) for t in line.tax_id
        )

    @staticmethod
    def _round_proforma(amount):
        return round(amount, 2)

    @api.depends(
        'order_line.discount',
        'order_line.price_unit',
        'order_line.product_uom_qty',
        'order_line.price_subtotal',
        'order_line.tax_id',
        'order_line.display_type',
        'order_line.is_downpayment',
        'amount_total',
        'currency_id',
    )
    def _compute_proforma_fiscal_totals(self):
        """Totales SAR para Factura Proforma (misma lógica que factura)."""
        for order in self:
            discount_total = 0.0
            exento = 0.0
            exonerado = 0.0
            isv15 = 0.0
            isv18 = 0.0
            importe15 = 0.0
            importe18 = 0.0
            for line in order._proforma_product_lines():
                if line.discount:
                    gross = line.product_uom_qty * line.price_unit
                    discount_total += abs(gross * (line.discount / 100.0))
                elif (
                    line.product_id
                    and line.product_id.product_tmpl_id.default_code == 'Desc'
                ):
                    discount_total += abs(line.price_subtotal)
                net_untaxed = line.price_subtotal
                if order._proforma_line_is_exempt(line):
                    exento += net_untaxed
                if order._proforma_line_is_exonerated(line):
                    exonerado += net_untaxed
                if (
                    order._proforma_line_is_exempt(line)
                    or order._proforma_line_is_exonerated(line)
                ):
                    continue
                base_imponible = line.price_subtotal
                for tax in line.tax_id:
                    if tax.tipo_impuesto != 'isv':
                        continue
                    if tax.amount == 15:
                        isv15 += order._round_proforma(base_imponible * 0.15)
                        importe15 += base_imponible
                    elif tax.amount == 18:
                        isv18 += order._round_proforma(base_imponible * 0.18)
                        importe18 += base_imponible
            currency = order.currency_id
            order.proforma_amount_discount = (
                currency.round(discount_total) if currency else discount_total
            )
            order.proforma_amount_exento = (
                currency.round(exento) if currency else exento
            )
            order.proforma_amount_exonerado = (
                currency.round(exonerado) if currency else exonerado
            )
            order.proforma_gravado_isv15 = order._round_proforma(importe15)
            order.proforma_gravado_isv18 = order._round_proforma(importe18)
            order.proforma_amount_isv15 = order._round_proforma(isv15)
            order.proforma_amount_isv18 = order._round_proforma(isv18)
            order.proforma_amount_words = (
                _num_util.numero_to_letras(order.amount_total)
                if order.amount_total else ''
            )

    def _get_sar_proforma_report_pages(self):
        """Paginación Factura Proforma (encabezado en cada página)."""
        self.ensure_one()
        lines = self.order_line.filtered(
            lambda line: line.display_type in ('line_section', 'line_note')
            or (not line.display_type and not line.is_downpayment)
        )
        # Proforma repite encabezado en todas las hojas → cupo bajo uniforme.
        return self._split_printable_report_pages(
            list(lines),
            lines,
            first_cap=12,
            middle_cap=12,
            last_cap=10,
            single_cap=10,
        )
