# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class KcTechnicalOrderpoint(models.Model):
    """Regla de abastecimiento por especificación técnica.

    A diferencia de `stock.warehouse.orderpoint` (nativo), que impone unicidad
    por (producto, ubicación) y por tanto solo admite UNA regla por producto,
    este modelo permite definir un mínimo por CADA configuración técnica del
    producto (varias reglas por producto, una por `technical_key`).

    El stock disponible se evalúa por especificación: suma de existencias de
    todos los lotes cuya `technical_key` coincide con la de la configuración.
    No interviene en el motor de reabastecimiento nativo de Odoo: estas reglas
    se consumen manualmente desde el asistente de Producción de Abastecimiento.
    """
    _name = 'kc.technical.orderpoint'
    _description = 'Regla de Abastecimiento por Especificación Técnica'
    _order = 'product_id, technical_key, id'

    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
        ondelete='cascade',
        index=True,
        domain="[('tracking', '=', 'lot')]",
    )
    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Plantilla de producto',
        related='product_id.product_tmpl_id',
        store=True,
    )
    product_uom = fields.Many2one(
        'uom.uom',
        string='Unidad de medida',
        related='product_id.uom_id',
    )
    technical_configuration_id = fields.Many2one(
        'product.technical.configuration',
        string='Configuración técnica',
        required=True,
        ondelete='restrict',
        index=True,
        domain="[('product_tmpl_id', '=', product_tmpl_id), ('active', '=', True)]",
        help='Especificación técnica concreta (matriz) cuyo mínimo se desea '
             'mantener en inventario.',
    )
    technical_key = fields.Char(
        string='Clave técnica',
        related='technical_configuration_id.technical_key',
        store=True,
        index=True,
    )
    technical_description = fields.Text(
        string='Especificaciones',
        related='technical_configuration_id.technical_description',
        store=True,
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Ubicación',
        required=True,
        ondelete='cascade',
        domain="[('usage', '=', 'internal')]",
        default=lambda self: self._default_location_id(),
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén',
        compute='_compute_warehouse_id',
        store=True,
    )
    product_min_qty = fields.Float(
        string='Cantidad mínima',
        digits='Product Unit of Measure',
        required=True,
        default=0.0,
        help='Si el stock de esta especificación cae por debajo de este valor, '
             'la regla sugiere producir.',
    )
    product_max_qty = fields.Float(
        string='Cantidad máxima',
        digits='Product Unit of Measure',
        default=0.0,
        help='Objetivo de stock al producir. Si es 0, se usa la cantidad mínima.',
    )
    qty_on_hand_spec = fields.Float(
        string='Existencias (especificación)',
        compute='_compute_spec_stock',
        digits='Product Unit of Measure',
    )
    qty_to_order_spec = fields.Float(
        string='A producir',
        compute='_compute_spec_stock',
        digits='Product Unit of Measure',
    )

    _sql_constraints = [
        (
            'technical_orderpoint_unique',
            'unique(product_id, location_id, technical_configuration_id, company_id)',
            'Ya existe una regla de abastecimiento para esta especificación '
            'técnica del producto en esta ubicación.',
        ),
    ]

    @api.model
    def _default_location_id(self):
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)
        return warehouse.lot_stock_id.id if warehouse else False

    @api.depends('location_id')
    def _compute_warehouse_id(self):
        Warehouse = self.env['stock.warehouse']
        for rule in self:
            warehouse = False
            if rule.location_id:
                warehouse = Warehouse.search([
                    ('lot_stock_id', 'parent_of', rule.location_id.id),
                ], limit=1) or Warehouse.search([
                    ('company_id', '=', rule.company_id.id),
                ], limit=1)
            rule.warehouse_id = warehouse.id if warehouse else False

    @api.depends(
        'product_id',
        'technical_key',
        'location_id',
        'product_min_qty',
        'product_max_qty',
    )
    def _compute_spec_stock(self):
        Quant = self.env['stock.quant']
        for rule in self:
            on_hand = 0.0
            if rule.technical_key and rule.product_id and rule.location_id:
                quants = Quant.search([
                    ('product_id', '=', rule.product_id.id),
                    ('location_id', 'child_of', rule.location_id.id),
                    ('lot_id.technical_key', '=', rule.technical_key),
                ])
                on_hand = sum(quants.mapped('quantity'))
            rule.qty_on_hand_spec = on_hand
            target = rule.product_max_qty if rule.product_max_qty > 0 else rule.product_min_qty
            if on_hand < rule.product_min_qty:
                rule.qty_to_order_spec = max(target - on_hand, 0.0)
            else:
                rule.qty_to_order_spec = 0.0

    @api.depends('product_id', 'technical_description', 'technical_key')
    def _compute_display_name(self):
        for rule in self:
            spec = (rule.technical_description or rule.technical_key or '').replace('\n', ', ')
            if rule.product_id and spec:
                rule.display_name = '%s [%s]' % (rule.product_id.display_name, spec)
            elif rule.product_id:
                rule.display_name = rule.product_id.display_name
            else:
                rule.display_name = _('Nueva regla técnica')

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for rule in self:
            config = rule.technical_configuration_id
            if config and rule.product_id and \
                    config.product_tmpl_id != rule.product_id.product_tmpl_id:
                rule.technical_configuration_id = False

    @api.constrains('technical_configuration_id', 'product_id')
    def _check_configuration_product(self):
        for rule in self:
            config = rule.technical_configuration_id
            if config and rule.product_id and \
                    config.product_tmpl_id != rule.product_id.product_tmpl_id:
                raise ValidationError(_(
                    'La configuración técnica "%(config)s" no pertenece al '
                    'producto "%(product)s".'
                ) % {
                    'config': config.display_name,
                    'product': rule.product_id.display_name,
                })

    @api.constrains('product_min_qty', 'product_max_qty')
    def _check_min_max(self):
        for rule in self:
            if rule.product_max_qty and rule.product_max_qty < rule.product_min_qty:
                raise ValidationError(_(
                    'La cantidad máxima no puede ser menor que la cantidad mínima.'
                ))

    def action_open_replenishment_wizard(self):
        """Abre el asistente de Producción de Abastecimiento (si está instalado
        el módulo de producción manual)."""
        action = self.env.ref(
            'kc_manual_production.kc_replenishment_rp_wizard_action',
            raise_if_not_found=False,
        )
        if not action:
            raise ValidationError(_(
                'El módulo de Producción Manual no está disponible para generar '
                'el registro de producción de abastecimiento.'
            ))
        return action.read()[0]
