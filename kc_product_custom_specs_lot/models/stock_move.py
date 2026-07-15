# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.tools.float_utils import float_is_zero


class StockMove(models.Model):
    _inherit = 'stock.move'

    kc_lot_id = fields.Many2one(
        'stock.lot',
        string='Lote técnico',
        copy=False,
        help='Lote de especificación técnica vinculado desde la línea de venta.',
    )
    lot_technical_description = fields.Text(
        related='kc_lot_id.technical_description',
        string='Descripción técnica del lote',
    )

    def _kc_get_sale_lot(self):
        self.ensure_one()
        return self.kc_lot_id or (self.sale_line_id.lot_id if self.sale_line_id else False)

    def _kc_should_restrict_lot_reservation(self):
        """True si la reserva/entrega debe limitarse por especificación técnica."""
        self.ensure_one()
        if not self.sale_line_id or self.picking_type_id.code != 'outgoing':
            return False
        sale_line = self.sale_line_id
        if not sale_line.technical_key:
            return False
        if hasattr(sale_line, '_requires_technical_specs'):
            return sale_line._requires_technical_specs()
        return bool(sale_line.technical_key)

    def _kc_get_restrict_reservation_lot(self):
        """Lote único legacy que debe reservarse (líneas antiguas con lot_id fijo)."""
        self.ensure_one()
        if not self._kc_should_restrict_lot_reservation():
            return self.env['stock.lot']
        sale_line = self.sale_line_id
        if sale_line.lot_id and sale_line.kc_lot_policy != 'production':
            return sale_line.lot_id
        return self.kc_lot_id or self.env['stock.lot']

    def _kc_should_restrict_by_technical_key(self):
        """Sin lote fijo en OV: reservar solo lotes con la misma technical_key."""
        self.ensure_one()
        if not self._kc_should_restrict_lot_reservation():
            return False
        return not self._kc_get_restrict_reservation_lot()

    def _kc_get_compatible_lots_for_reservation(self):
        self.ensure_one()
        sale_line = self.sale_line_id
        if not sale_line or not sale_line.technical_key:
            return self.env['stock.lot']
        return self.env['stock.lot'].search([
            ('product_id', '=', self.product_id.id),
            ('technical_key', '=', sale_line.technical_key),
        ])

    def _update_reserved_quantity(self, need, location_id, lot_id=None,
                                  package_id=None, owner_id=None, strict=True):
        restrict_lot = self._kc_get_restrict_reservation_lot()
        if restrict_lot:
            lot_id = restrict_lot
            strict = True
            return super()._update_reserved_quantity(
                need, location_id, lot_id=lot_id, package_id=package_id,
                owner_id=owner_id, strict=strict,
            )
        if self._kc_should_restrict_by_technical_key():
            return self._kc_update_reserved_quantity_by_technical_key(
                need, location_id, package_id=package_id, owner_id=owner_id,
            )
        return super()._update_reserved_quantity(
            need, location_id, lot_id=lot_id, package_id=package_id,
            owner_id=owner_id, strict=strict,
        )

    def _kc_update_reserved_quantity_by_technical_key(
            self, need, location_id, package_id=None, owner_id=None):
        """Reserva iterando lotes compatibles por technical_key (multi-lote)."""
        self.ensure_one()
        rounding = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        remaining = need
        total_taken = 0.0
        compatible_lots = self._kc_get_compatible_lots_for_reservation()
        for lot in compatible_lots:
            if float_is_zero(remaining, precision_rounding=rounding):
                break
            taken = super(StockMove, self)._update_reserved_quantity(
                remaining,
                location_id,
                lot_id=lot,
                package_id=package_id,
                owner_id=owner_id,
                strict=True,
            )
            total_taken += taken
            remaining -= taken
        return total_taken

    def _prepare_move_line_vals(self, quantity=None, reserved_quant=None):
        vals = super()._prepare_move_line_vals(
            quantity=quantity,
            reserved_quant=reserved_quant,
        )
        lot = self._kc_get_restrict_reservation_lot()
        if lot and self._kc_should_restrict_lot_reservation():
            vals['lot_id'] = lot.id
        return vals

    def _kc_reassign_restricted_lot(self):
        """Re-reserva si la asignación automática usó lotes incorrectos."""
        for move in self:
            if not move._kc_should_restrict_lot_reservation():
                continue
            sale_line = move.sale_line_id
            restrict_lot = move._kc_get_restrict_reservation_lot()
            if restrict_lot:
                wrong_lines = move.move_line_ids.filtered(
                    lambda ml: ml.lot_id and ml.lot_id != restrict_lot)
                missing_correct = not move.move_line_ids.filtered(
                    lambda ml: ml.lot_id == restrict_lot)
                if wrong_lines or missing_correct:
                    move._do_unreserve()
                    move._action_assign()
                continue
            tech_key = sale_line.technical_key
            wrong_lines = move.move_line_ids.filtered(
                lambda ml: ml.lot_id and ml.lot_id.technical_key != tech_key
            )
            if wrong_lines:
                move._do_unreserve()
                move._action_assign()


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    lot_technical_description = fields.Text(
        related='lot_id.technical_description',
        string='Descripción técnica',
    )
    sale_technical_key = fields.Char(
        related='move_id.sale_line_id.technical_key',
        string='Clave técnica venta',
    )
    kc_allowed_lot_ids = fields.Many2many(
        comodel_name='stock.lot',
        compute='_compute_kc_allowed_lot_ids',
        string='Lotes permitidos',
    )

    @api.depends(
        'product_id',
        'move_id.sale_line_id.technical_key',
        'move_id.sale_line_id.order_id',
        'move_id.picking_type_id.code',
    )
    def _compute_kc_allowed_lot_ids(self):
        Lot = self.env['stock.lot']
        for ml in self:
            if not ml.product_id:
                ml.kc_allowed_lot_ids = Lot
                continue
            sale_line = ml.move_id.sale_line_id
            tech_key = sale_line.technical_key if sale_line else False
            if (ml.move_id.picking_type_id.code == 'outgoing' and tech_key
                    and sale_line._requires_technical_specs()):
                compatible = Lot.search([
                    ('product_id', '=', ml.product_id.id),
                    ('technical_key', '=', tech_key),
                ])
                order = sale_line.order_id
                if order and 'kc_entry_id' in Lot._fields:
                    rp_lots = compatible.filtered(
                        lambda lot: lot.kc_entry_id
                        and lot.kc_sale_order_id == order
                    )
                    ml.kc_allowed_lot_ids = rp_lots | (compatible - rp_lots)
                else:
                    ml.kc_allowed_lot_ids = compatible
            else:
                ml.kc_allowed_lot_ids = Lot.search([
                    ('product_id', '=', ml.product_id.id),
                ])
