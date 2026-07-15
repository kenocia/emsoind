# -*- coding: utf-8 -*-
"""Asegura que Operador de Bodega implique Usuario de Inventario (validar RP)."""


def migrate(cr, version):
    cr.execute("""
        SELECT res_id FROM ir_model_data
        WHERE module = 'kc_manual_production'
          AND name = 'kc_production_group_bodega'
          AND model = 'res.groups'
        LIMIT 1
    """)
    row = cr.fetchone()
    if not row:
        return
    bodega_gid = row[0]
    cr.execute("""
        SELECT res_id FROM ir_model_data
        WHERE module = 'stock'
          AND name = 'group_stock_user'
          AND model = 'res.groups'
        LIMIT 1
    """)
    row = cr.fetchone()
    if not row:
        return
    stock_user_gid = row[0]
    cr.execute("""
        INSERT INTO res_groups_implied_rel (gid, hid)
        SELECT %s, %s
        WHERE NOT EXISTS (
            SELECT 1 FROM res_groups_implied_rel WHERE gid = %s AND hid = %s
        )
    """, (bodega_gid, stock_user_gid, bodega_gid, stock_user_gid))
