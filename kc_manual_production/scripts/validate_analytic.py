# -*- coding: utf-8 -*-
"""Validación de distribución analítica RP/CMP (Odoo 18).

Ejecutar en una instancia de prueba con:

    odoo shell -d <db> --db_host=db --db_user=odoo --db_password=...
    >>> exec(open('/mnt/extra-addons/kc_manual_production/scripts/validate_analytic.py').read())

El script hace ROLLBACK al final: NO persiste datos. Requiere productos con
valoración 'Automática / tiempo real' (categoría con property_valuation='real_time')
para que se generen asientos y líneas analíticas.

Cubre:
  1) RP ligado a OV con proyecto/cuenta analítica -> línea analítica POSITIVA.
  2) CMP ligado al RP (hereda la misma analítica)  -> línea analítica NEGATIVA.
  3) CMP de merma con reparto manual 60/40         -> 2 líneas analíticas.
  4) Reversión del CMP del punto 2                 -> línea inversa, netea a 0.
"""

OK = "[OK]"
ERR = "[ERROR]"


def _f(x):
    return round(float(x or 0.0), 2)


def run(env):
    AAccount = env['account.analytic.account']
    ALine = env['account.analytic.line']
    Plan = env['account.analytic.plan']
    company = env.company

    print("=" * 70)
    print("VALIDACIÓN DISTRIBUCIÓN ANALÍTICA - kc_manual_production")
    print("=" * 70)

    plan = Plan.search([], limit=1) or Plan.create({'name': 'Plan Test KC'})
    cuenta_ov = AAccount.create({'name': 'KC OV Proyecto', 'plan_id': plan.id})
    cuenta_a = AAccount.create({'name': 'KC Depto A', 'plan_id': plan.id})
    cuenta_b = AAccount.create({'name': 'KC Depto B', 'plan_id': plan.id})

    # --- Producto PT (vendible, lote, valoración real_time) ----------------
    categ = env['product.category'].create({
        'name': 'KC Categoría real_time',
        'property_cost_method': 'standard',
        'property_valuation': 'real_time',
    })
    pt = env['product.product'].create({
        'name': 'KC PT Analítica', 'type': 'consu', 'is_storable': True,
        'tracking': 'lot', 'sale_ok': True, 'standard_price': 100.0,
        'categ_id': categ.id,
    })
    mp = env['product.product'].create({
        'name': 'KC MP Analítica', 'type': 'consu', 'is_storable': True,
        'tracking': 'none', 'sale_ok': False, 'standard_price': 40.0,
        'categ_id': categ.id,
    })

    partner = env['res.partner'].create({'name': 'KC Cliente Test'})

    # --- Orden de venta con proyecto -> cuenta analítica -------------------
    so = env['sale.order'].create({
        'partner_id': partner.id,
        'order_line': [(0, 0, {'product_id': pt.id, 'product_uom_qty': 5.0})],
    })
    if 'project_id' in so._fields:
        proyecto = env['project.project'].create({
            'name': 'KC Proyecto Test', 'account_id': cuenta_ov.id,
        })
        so.project_id = proyecto.id
    so.action_confirm()

    Entry = env['kc.production.entry']
    Cons = env['kc.production.consumption']

    # --- Helper de herencia ------------------------------------------------
    dist = Entry._kc_sale_analytic_distribution(so)
    esperado = {str(cuenta_ov.id): 100.0}
    print(f"\n1) Herencia desde OV: {dist}")
    print(f"   {OK if dist == esperado else ERR} esperado {esperado}")

    # --- Escenario 1: RP ---------------------------------------------------
    rp = Entry.create({
        'sale_order_id': so.id, 'partner_id': partner.id,
        'line_ids': [(0, 0, {'product_id': pt.id, 'qty': 5.0})],
    })
    print(f"\n2) RP.analytic_distribution = {rp.analytic_distribution}")
    print(f"   {OK if rp.analytic_distribution == esperado else ERR}")
    rp.action_confirm()
    rp.action_validate()
    rp_moves = rp.picking_id.move_ids
    rp_alines = rp_moves.mapped('analytic_account_line_ids')
    rp_amount = sum(rp_alines.mapped('amount'))
    print(f"   Líneas analíticas RP: {len(rp_alines)} | suma amount = {_f(rp_amount)}")
    print(f"   {OK if rp_amount > 0 else ERR} debe ser POSITIVO (entrada PT)")
    print(f"   Asientos contables RP (smart button): {rp.account_move_count}")

    # --- Escenario 2: CMP ligado al RP ------------------------------------
    cmp1 = Cons.create({'entry_id': rp.id})
    cmp1._onchange_entry_id()
    cmp1._onchange_kc_analytic_distribution()
    cmp1.write({'line_ids': [(0, 0, {'product_id': mp.id, 'qty': 3.0})]})
    print(f"\n3) CMP.analytic_distribution heredada = {cmp1.analytic_distribution}")
    print(f"   {OK if cmp1.analytic_distribution == esperado else ERR}")
    # Requiere stock de MP; lo creamos vía inventario rápido.
    env['stock.quant']._update_available_quantity(
        mp, rp.location_id, 10.0)
    cmp1.action_confirm()
    cmp1.action_validate()
    cmp1_alines = cmp1.picking_id.move_ids.mapped('analytic_account_line_ids')
    cmp1_amount = sum(cmp1_alines.mapped('amount'))
    print(f"   Líneas analíticas CMP: {len(cmp1_alines)} | suma amount = {_f(cmp1_amount)}")
    print(f"   {OK if cmp1_amount < 0 else ERR} debe ser NEGATIVO (costo)")

    # --- Escenario 3: CMP merma con reparto 60/40 -------------------------
    cmp2 = Cons.create({
        'analytic_distribution': {str(cuenta_a.id): 60.0, str(cuenta_b.id): 40.0},
        'line_ids': [(0, 0, {'product_id': mp.id, 'qty': 2.0})],
    })
    env['stock.quant']._update_available_quantity(mp, cmp2._get_warehouse().lot_stock_id, 10.0)
    cmp2.action_confirm()
    cmp2.action_validate()
    cmp2_alines = cmp2.picking_id.move_ids.mapped('analytic_account_line_ids')
    por_cuenta = {}
    for al in cmp2_alines:
        por_cuenta[al.account_id.name] = _f(por_cuenta.get(al.account_id.name, 0) + al.amount)
    print(f"\n4) CMP merma 60/40 -> {len(cmp2_alines)} líneas: {por_cuenta}")
    print(f"   {OK if len(cmp2_alines) == 2 else ERR} deben ser 2 líneas (una por depto)")

    # --- Escenario 4: reversión del CMP del punto 2 -----------------------
    rev = cmp1.create_reversal("Prueba reversión analítica")
    rev_alines = rev.picking_id.move_ids.mapped('analytic_account_line_ids')
    rev_amount = sum(rev_alines.mapped('amount'))
    neto = _f(cmp1_amount + rev_amount)
    print(f"\n5) Reversión CMP: suma amount = {_f(rev_amount)} (original {_f(cmp1_amount)})")
    print(f"   Neto original+reversión = {neto}")
    print(f"   {OK if abs(neto) < 0.01 and rev_amount > 0 else ERR} debe netear a 0")

    print("\n" + "=" * 70)
    print("Haciendo ROLLBACK (no se persiste nada)...")
    env.cr.rollback()
    print("Listo.")


try:
    run(env)  # noqa: F821  (env existe en odoo shell)
except Exception as exc:  # noqa: BLE001
    import traceback
    traceback.print_exc()
    try:
        env.cr.rollback()  # noqa: F821
    except Exception:
        pass
    print(f"{ERR} La validación abortó: {exc}")
