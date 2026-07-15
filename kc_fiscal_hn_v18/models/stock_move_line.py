# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from datetime import datetime


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    # Campos del módulo original
    partner_id = fields.Many2one(comodel_name='res.partner', string='Contacto', required=False,
                                 related='picking_id.partner_id')
    quantity_real = fields.Float(
        'Quantity', digits='Product Unit of Measure', copy=False, store=True,
        compute='_compute_qty_real', readonly=False)
    unit_cost = fields.Float('Costo', digits='Product Price', store=True)
    total_cost = fields.Float(string='Total Costo', required=False, compute='_calculate_total_cost', store=True)
    purchase_order_id = fields.Many2one('purchase.order', string='Pedido de Compra', compute='_get_purchaseorder',
                                        store=True)
    sale_order_id = fields.Many2one('sale.order', string='Pedido de Venta', compute='_get_saleorder', store=True)
    invoice_ids = fields.Many2many('account.move', string='Facturas',
                                   compute='_get_invoiced_supplier', store=True)
    on_hand = fields.Float('Residual', digits='Product Unit of Measure', store=True,
                           compute='_compute_available_quantities')
    total_cost_on_hand = fields.Float('Total Residual', digits='Product Price', store=True)
    previous_available_quantity = fields.Float(string='Previous Qty',
                                               compute='_compute_available_quantities', store=True)
    location_own_id = fields.Many2one('stock.location', 'Ubicacion', check_company=True, compute="_get_location",
                                      store=True, readonly=False)

    # Campos fiscales para líneas de movimiento de stock (del módulo migrado)
    base_imponible = fields.Float(string='Base Imponible', compute='_compute_base_imponible', store=True)
    monto_isv = fields.Float(string='Monto ISV', compute='_compute_monto_isv', store=True)

    def _history_cost(self):
        formato = "%Y-%m-%d %H:%M:%S"
        for r in self:
            domain = [('stock_move_id', '=', r.move_id.id),
                      ('product_id', '=', r.product_id.id),
                      ('quantity', '=', r.quantity)]
            domain2 = [('stock_move_id', '=', r.move_id.id),
                       ('product_id', '=', r.product_id.id),
                       ('reference', '=', r.reference),
                       ('quantity', '!=', 0)]
            valuation_layer = self.env['stock.valuation.layer'].search(domain)
            if valuation_layer:
                for i in valuation_layer:
                    if r.quantity_real == i.remaining_qty:
                        r.unit_cost = round(i.remaining_value / r.quantity_real, 4)
                        r._calculate_total_cost()
                    elif r.quantity_real == i.quantity:
                        r.unit_cost = round(i.value / r.quantity_real, 4)
                        r._calculate_total_cost()
                    else:
                        r.unit_cost = round(i.unit_cost, 4)
                        r._calculate_total_cost()
            else:
                valuation_layer = self.env['stock.valuation.layer'].search(domain2)
                for i in valuation_layer:
                    if r.quantity_real == i.remaining_qty:
                        r.unit_cost = round(i.remaining_value / r.quantity_real, 4)
                        r._calculate_total_cost()
                    elif r.quantity_real == i.quantity:
                        r.unit_cost = round(i.value / r.quantity_real, 4)
                        r._calculate_total_cost()
                    else:
                        r.unit_cost = round(i.remaining_value / r.quantity_real, 4)
                        r._calculate_total_cost()

    def _history_cost_specialist(self):
        formato = "%Y-%m-%d %H:%M:%S"
        for r in self:
            domain2 = [('stock_move_id', '=', r.move_id.id),
                       ('product_id', '=', r.product_id.id),
                       ('reference', '=', r.reference)]
            valuation_layer = self.env['stock.valuation.layer'].search(domain2)
            if valuation_layer:
                total_account = 0
                total_unit = 0
                for i in valuation_layer:
                    if abs(i.remaining_value) > abs(i.value):
                        total_account += i.remaining_value
                        try:
                            r.unit_cost = round(total_account / i.quantity, 4)
                        except ZeroDivisionError:
                            r.unit_cost = 0
                        r._calculate_total_cost()
                        return True
                    else:
                        total_account += i.value
                        total_unit += i.quantity
                        if i.quantity == 0:
                            try:
                                r.unit_cost = round(total_account / total_unit, 4)
                            except ZeroDivisionError:
                                r.unit_cost = 0
                        else:
                            try:
                                r.unit_cost = round(total_account / i.quantity, 4)
                            except ZeroDivisionError:
                                r.unit_cost = 0
                        r._calculate_total_cost()
                return True
            else:
                return False

    def _set_prom_price(self):
        for m in self:
            if m.product_id:
                m.unit_cost = m.product_id.standard_price
                m.total_cost = m.quantity_real * m.unit_cost

    def _save_move_line(self):
        for r in self:
            status = r._history_cost_specialist()
            if status == False:
                r._history_cost()
            r._get_location()
            if r.unit_cost == 0:
                r._set_prom_price()

    def _calculate_total_cost(self):
        for m in self:
            if m.product_id:
                m.total_cost = m.quantity_real * m.unit_cost

    @api.depends("quantity")
    def _compute_qty_real(self):
        for q in self:
            if q.picking_id.picking_type_code == 'outgoing':
                q.quantity_real = -q.quantity
            else:
                q.quantity_real = q.quantity

    @api.depends("picking_id", "picking_id.purchase_id")
    def _get_purchaseorder(self):
        """Pedido de compra vinculado al albarán (campo purchase_id aportado por purchase_stock)."""
        for move in self:
            picking = move.picking_id
            if not picking:
                move.purchase_order_id = False
                continue
            if "purchase_id" in picking._fields:
                move.purchase_order_id = picking.purchase_id
            else:
                move.purchase_order_id = False

    @api.depends("picking_id")
    def _get_saleorder(self):
        for move in self:
            if move.picking_id.origin:
                # Buscar la orden de venta usando el origin del picking
                sale_order = self.env['sale.order'].search([
                    ('name', '=', move.picking_id.origin)
                ], limit=1)
                if sale_order:
                    move.sale_order_id = sale_order.id
                else:
                    move.sale_order_id = False
            else:
                move.sale_order_id = False

    @api.depends("picking_id")
    def _get_invoiced_supplier(self):
        for move in self:
            if move.purchase_order_id:
                invoices = move.purchase_order_id.invoice_ids
                for r in invoices:
                    move.invoice_ids = [(4, r.id, 0)]
            if move.sale_order_id:
                invoices = move.sale_order_id.invoice_ids
                for r in invoices:
                    move.invoice_ids = [(4, r.id, 0)]

    @api.depends('location_id', 'location_dest_id')
    def _get_location(self):
        for loc in self:
            if loc.picking_id.picking_type_code == 'incoming':
                loc.location_own_id = loc.location_dest_id
            elif loc.picking_id.picking_type_code == 'outgoing':
                loc.location_own_id = loc.location_id
            else:
                loc.location_own_id = loc.location_dest_id

    @api.depends('product_id', 'location_id', 'location_dest_id')
    def _compute_available_quantities(self):
        for line in self:
            line.on_hand = 0
            line.previous_available_quantity = 0

            # Obtener la cantidad disponible en la ubicación de destino (línea anterior)
            previous_lines = self.search([
                ('product_id', '=', line.product_id.id),
                ('id', '<', line.id),
                ('state', '=', 'done')
            ], order='id asc')
            previous_available_qty = sum(previous_lines.mapped('quantity_real')) if previous_lines else 0
            previous_available_total = sum(previous_lines.mapped('total_cost')) if previous_lines else 0
            line.previous_available_quantity = previous_available_qty
            line.on_hand = line.previous_available_quantity + line.quantity_real
            if line.quantity_real > 0:
                line.total_cost_on_hand = round(previous_available_total + line.total_cost, 2)
            else:
                line.total_cost_on_hand = round(line.on_hand * line.unit_cost, 2)

    # Métodos fiscales del módulo migrado
    @api.depends('product_id', 'qty_done', 'product_uom_id')
    def _compute_base_imponible(self):
        for line in self:
            if line.product_id and line.qty_done:
                # Calcular base imponible basada en el costo del producto
                cost = line.product_id.standard_price
                line.base_imponible = cost * line.qty_done
            else:
                line.base_imponible = 0.0
    
    @api.depends('base_imponible', 'product_id')
    def _compute_monto_isv(self):
        for line in self:
            if line.product_id and line.base_imponible:
                # Obtener impuestos ISV del producto
                isv_taxes = line.product_id.taxes_id.filtered(lambda t: t.tipo_impuesto == 'isv')
                if isv_taxes:
                    # Calcular ISV basado en el primer impuesto ISV encontrado
                    tax_amount = (line.base_imponible * isv_taxes[0].amount) / 100
                    line.monto_isv = tax_amount
                else:
                    line.monto_isv = 0.0
            else:
                line.monto_isv = 0.0
