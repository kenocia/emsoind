# -*- coding: utf-8 -*-
"""Backfill origin_type en bloques de plan existentes."""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    Plan = env['kc.production.plan.line']
    with_ov = Plan.search([('sale_order_line_id', '!=', False)])
    without_ov = Plan.search([('sale_order_line_id', '=', False)])
    if with_ov:
        with_ov.write({'origin_type': 'sale_order'})
    if without_ov:
        without_ov.write({'origin_type': 'replenishment'})
    # Alinear producto con línea OV
    fixed = 0
    for rec in with_ov:
        if rec.sale_order_line_id and rec.product_id != rec.sale_order_line_id.product_id:
            rec.product_id = rec.sale_order_line_id.product_id
            fixed += 1
    _logger.info(
        'kc_manual_production 18.0.1.25.0: origin_type OV=%s abastecimiento=%s; '
        'productos alineados=%s',
        len(with_ov), len(without_ov), fixed,
    )
