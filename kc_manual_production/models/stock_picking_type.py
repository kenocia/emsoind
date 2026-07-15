# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPickingType(models.Model):
    """Extiende los tipos de operación para marcar los usados por el módulo.

    El marcador kc_production_role permite que el RP/CMP localicen su tipo de
    operación dedicado de forma fiable (por rol, no por nombre ni por orden),
    funcionando correctamente en entornos multi-compañía.
    """
    _inherit = 'stock.picking.type'

    kc_production_role = fields.Selection(
        selection=[
            ('rp', 'Producción Manual - Entrada (RP)'),
            ('cmp', 'Consumo Materia Prima - Salida (CMP)'),
        ],
        string='Rol Producción Manual KC',
        copy=False,
        index=True,
        help="Marca este tipo de operación como el usado por el módulo de "
             "Producción Manual KC para entradas de PT (rp) o salidas de MP (cmp).",
    )

    @api.model
    def _kc_get_or_create_production_type(self, role, company):
        """Devuelve (creándolo si hace falta) el tipo de operación dedicado.

        role: 'rp' (entrada Producción→Stock) o 'cmp' (salida Stock→Producción).
        Crea el tipo con las ubicaciones y la configuración de lotes correctas
        (incluido use_existing_lots=True, indispensable para asignar lotes ya
        existentes). Resuelve la ubicación de Producción de la compañía.
        """
        existing = self.search([
            ('kc_production_role', '=', role),
            ('company_id', '=', company.id),
        ], limit=1)
        if existing:
            return existing

        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1)
        if not warehouse:
            return self.browse()

        # Ubicación de Producción de la compañía (o compartida company_id=False).
        prod_loc = self.env['stock.location'].search([
            ('usage', '=', 'production'),
            ('company_id', 'in', [company.id, False]),
        ], order='company_id desc', limit=1)
        if not prod_loc:
            prod_loc = self.env.ref('stock.location_production', raise_if_not_found=False)
        if not prod_loc:
            return self.browse()

        stock_loc = warehouse.lot_stock_id
        Location = self.env['stock.location']
        pt_loc = Location.search([
            ('usage', '=', 'internal'),
            ('company_id', '=', company.id),
            ('complete_name', 'ilike', '%Bodega PT%'),
        ], limit=1)
        mp_loc = Location.search([
            ('usage', '=', 'internal'),
            ('company_id', '=', company.id),
            ('complete_name', 'ilike', '%Bodega MP%'),
        ], limit=1)

        if role == 'rp':
            dest_loc = pt_loc or stock_loc
            vals = {
                'name': 'Producción Manual (RP)',
                'code': 'incoming',
                'sequence_code': 'RP',
                'warehouse_id': warehouse.id,
                'company_id': company.id,
                'default_location_src_id': prod_loc.id,
                'default_location_dest_id': dest_loc.id,
                'use_create_lots': True,
                'use_existing_lots': True,
                'kc_production_role': 'rp',
            }
        else:  # 'cmp'
            src_loc = mp_loc or stock_loc
            vals = {
                'name': 'Consumo MP (CMP)',
                'code': 'outgoing',
                'sequence_code': 'CMP',
                'warehouse_id': warehouse.id,
                'company_id': company.id,
                'default_location_src_id': src_loc.id,
                'default_location_dest_id': prod_loc.id,
                'use_create_lots': False,
                'use_existing_lots': True,
                'kc_production_role': 'cmp',
            }
        return self.create(vals)
