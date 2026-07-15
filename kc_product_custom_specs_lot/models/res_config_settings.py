# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    kc_lot_creation_mode = fields.Selection(
        selection=[
            ('from_rp', 'Desde Registro de Producción (recomendado)'),
            ('from_mrp', 'Desde orden de producción MRP'),
            ('manual_pin', 'Creación manual con PIN (legacy)'),
        ],
        string='Creación de lotes técnicos',
        default='from_rp',
        config_parameter='kc_product_custom_specs_lot.lot_creation_mode',
    )
    kc_require_pin_lot_creation = fields.Boolean(
        string='Exigir PIN para crear lote',
        default=True,
        config_parameter='kc_product_custom_specs_lot.require_pin_lot_creation',
    )
    kc_auto_open_specs_wizard = fields.Boolean(
        string='Abrir modal al elegir producto',
        default=True,
        config_parameter='kc_product_custom_specs_lot.auto_open_specs_wizard',
    )
