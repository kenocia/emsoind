# -*- coding: utf-8 -*-
"""
Script de validación de _resolve_or_create_lot — kc_manual_production
Ejecutar dentro del shell de Odoo (en tu instancia Odoo 18 con el módulo
kc_manual_production instalado):

    odoo shell -d TU_BASE < .../scripts/validate_lot_resolution.py

o, con Docker:

    docker compose exec -T web odoo shell -d TU_BASE \
        < custom-addons/kc_manual_production/scripts/validate_lot_resolution.py

Comprueba la REGLA DE NEGOCIO del lote en orden estricto:
    PASO 1 — Si la línea de la OV ya tiene lote, se respeta SIEMPRE
             (sin importar el tipo de producto).
    PASO 2 — Solo si no hay lote, se crea según el TIPO DE PRODUCTO
             (specs técnicas vs. lote simple).

Escenarios:
    A) producto "specs" CON lot_id en la OV  -> usa ese lote, no crea nada.
    B) producto "specs" SIN lot_id           -> crea vía _get_or_create_for_sale_line.
    C) producto "simple" SIN lot_id          -> crea LOT-{RP}-{code}-{seq}.
    D) producto "simple" CON lot_id (raro)   -> usa ese lote, no crea nada.

IMPORTANTE: al final hace env.cr.rollback() para NO dejar datos de prueba en
la base. No se persiste nada.
"""

resultados = []

OK_MARK = "\u2713"      # check
WARN_MARK = "\u26a0"    # warning
DASH = "\u2014"         # em dash


def check(nombre, condicion, detalle=""):
    estado = "OK" if condicion else "FALLO"
    marca = OK_MARK if condicion else WARN_MARK
    resultados.append((condicion, nombre, detalle))
    detalle_txt = f" {DASH} {detalle}" if detalle else ""
    print(f"{marca} {estado} {DASH} {nombre}{detalle_txt}")


print("=" * 70)
print("VALIDACI\u00d3N _resolve_or_create_lot \u2014 kc_manual_production")
print("=" * 70)

company = env.company
Lot = env['stock.lot']
Tmpl = env['product.template']

# ¿Está disponible el módulo de especificaciones técnicas?
specs_installed = (
    hasattr(Lot, '_get_or_create_for_sale_line')
    and 'technical_attribute_line_ids' in Tmpl._fields
)
print(f"\nM\u00f3dulo kc_product_custom_specs_lot detectado: {specs_installed}")


def lot_count(product):
    return Lot.search_count([('product_id', '=', product.id)])


# ---------------------------------------------------------------
# SETUP: productos, atributo técnico, partner y orden de venta
# ---------------------------------------------------------------
print("\n--- SETUP ---")

partner = env['res.partner'].create({'name': 'TEST_KC Cliente Lotes'})

# Producto SIMPLE (sin atributos técnicos), almacenable, rastreo por lote.
tmpl_simple = Tmpl.create({
    'name': 'TEST_KC Producto Simple',
    'type': 'consu',
    'is_storable': True,
    'tracking': 'lot',
})
simple_product = tmpl_simple.product_variant_id
print(f"Producto simple: {simple_product.display_name} (id={simple_product.id})")

specs_product = None
attr = None
if specs_installed:
    attr = env['custom.technical.attribute'].create({
        'name': 'TEST Medida',
        'code': 'test_kc_medida',
        'display_type': 'text',
    })
    tmpl_specs = Tmpl.create({
        'name': 'TEST_KC Producto Specs',
        'type': 'consu',
        'is_storable': True,
        'tracking': 'lot',
        'technical_attribute_line_ids': [(0, 0, {
            'attribute_id': attr.id,
            'required': True,
        })],
    })
    specs_product = tmpl_specs.product_variant_id
    print(f"Producto specs: {specs_product.display_name} (id={specs_product.id})")
else:
    print("(Se omiten escenarios A y B: el m\u00f3dulo de specs no est\u00e1 instalado)")

so = env['sale.order'].create({'partner_id': partner.id})


def crear_linea_ov(product, qty=5, con_specs=False, value_text='SPEC'):
    vals = {
        'order_id': so.id,
        'product_id': product.id,
        'product_uom_qty': qty,
    }
    if con_specs and attr is not None:
        vals['technical_value_ids'] = [(0, 0, {
            'attribute_id': attr.id,
            'value_text': value_text,
            'required': True,
        })]
    return env['sale.order.line'].with_context(kc_from_specs_wizard=True).create(vals)


def crear_rp(product, ov_line, lot_id=False):
    line_vals = {
        'product_id': product.id,
        'qty': ov_line.product_uom_qty,
        'sale_order_line_id': ov_line.id,
    }
    if lot_id:
        line_vals['lot_id'] = lot_id
    return env['kc.production.entry'].create({
        'sale_order_id': so.id,
        'company_id': company.id,
        'line_ids': [(0, 0, line_vals)],
    })


# ---------------------------------------------------------------
# ESCENARIO A — specs + OV ya tiene lote -> se respeta, no crea
# ---------------------------------------------------------------
print("\n--- ESCENARIO A: specs CON lot_id en la OV ---")
if specs_installed:
    line_a = crear_linea_ov(specs_product, con_specs=True, value_text='SPEC-A')
    lot_a = Lot.create({
        'name': 'TEST_KC PREEXISTENTE A',
        'product_id': specs_product.id,
        'company_id': company.id,
    })
    line_a.with_context(kc_from_specs_wizard=True).write({'lot_id': lot_a.id})

    antes = lot_count(specs_product)
    rp_a = crear_rp(specs_product, line_a, lot_id=lot_a.id)
    rp_a.action_confirm()
    despues = lot_count(specs_product)

    lote_resuelto = rp_a.line_ids.lot_id
    check("A) usa el lote existente de la OV", lote_resuelto == lot_a,
          f"resuelto={lote_resuelto.name}")
    check("A) NO crea lote nuevo", antes == despues,
          f"antes={antes} despues={despues}")
    check("A) sella kc_entry_id en el lote", lote_resuelto.kc_entry_id == rp_a,
          f"kc_entry_id={lote_resuelto.kc_entry_id.id}")
else:
    print("(omitido)")

# ---------------------------------------------------------------
# ESCENARIO B — specs + sin lote -> crea vía specs y refleja en OV
# ---------------------------------------------------------------
print("\n--- ESCENARIO B: specs SIN lot_id ---")
if specs_installed:
    line_b = crear_linea_ov(specs_product, con_specs=True, value_text='SPEC-B')
    check("B) la l\u00ednea de OV tiene technical_key", bool(line_b.technical_key),
          f"technical_key={line_b.technical_key!r}")

    antes = lot_count(specs_product)
    rp_b = crear_rp(specs_product, line_b)
    rp_b.action_confirm()
    despues = lot_count(specs_product)

    lote_b = rp_b.line_ids.lot_id
    check("B) crea un lote nuevo", despues == antes + 1,
          f"antes={antes} despues={despues}")
    check("B) el lote nace con technical_key (v\u00eda specs)",
          bool(getattr(lote_b, 'technical_key', False)),
          f"technical_key={getattr(lote_b, 'technical_key', None)!r}")
    check("B) refleja el lote en la l\u00ednea de la OV", line_b.lot_id == lote_b,
          f"ov_line.lot_id={line_b.lot_id.name}")
else:
    print("(omitido)")

# ---------------------------------------------------------------
# ESCENARIO C — simple + sin lote -> crea LOT-{RP}-{code}-{seq}
# ---------------------------------------------------------------
print("\n--- ESCENARIO C: simple SIN lot_id ---")
line_c = crear_linea_ov(simple_product)
antes = lot_count(simple_product)
rp_c = crear_rp(simple_product, line_c)
rp_c.action_confirm()
despues = lot_count(simple_product)

lote_c = rp_c.line_ids.lot_id
check("C) crea un lote nuevo", despues == antes + 1,
      f"antes={antes} despues={despues}")
check("C) el lote sigue el patr\u00f3n LOT-{RP}-...",
      bool(lote_c.name and lote_c.name.startswith(f"LOT-{rp_c.name}-")),
      f"nombre={lote_c.name}")
check("C) refleja el lote en la l\u00ednea de la OV", line_c.lot_id == lote_c,
      f"ov_line.lot_id={line_c.lot_id.name}")

# ---------------------------------------------------------------
# ESCENARIO D — simple + lote puesto por error -> se respeta
# ---------------------------------------------------------------
print("\n--- ESCENARIO D: simple CON lot_id (inconsistente) ---")
line_d = crear_linea_ov(simple_product)
lot_d = Lot.create({
    'name': 'TEST_KC PREEXISTENTE D',
    'product_id': simple_product.id,
    'company_id': company.id,
})
line_d.with_context(kc_from_specs_wizard=True).write({'lot_id': lot_d.id})

antes = lot_count(simple_product)
rp_d = crear_rp(simple_product, line_d, lot_id=lot_d.id)
rp_d.action_confirm()
despues = lot_count(simple_product)

lote_d = rp_d.line_ids.lot_id
check("D) usa el lote existente (PASO 1 manda sobre el tipo)", lote_d == lot_d,
      f"resuelto={lote_d.name}")
check("D) NO crea lote nuevo", antes == despues,
      f"antes={antes} despues={despues}")

# ---------------------------------------------------------------
# RESUMEN
# ---------------------------------------------------------------
print("\n" + "=" * 70)
print("RESUMEN")
print("=" * 70)
fallos = [r for r in resultados if not r[0]]
for ok, nombre, _detalle in resultados:
    print(f"{OK_MARK if ok else WARN_MARK}  {nombre}")
print("-" * 70)
if fallos:
    print(f"{WARN_MARK}  {len(fallos)} comprobaci\u00f3n(es) FALLARON. Revisa arriba.")
else:
    print(f"{OK_MARK} Las {len(resultados)} comprobaciones pasaron correctamente.")
print("-" * 70)

# Rollback: no dejar datos de prueba en la base.
env.cr.rollback()
print("\n(Se hizo rollback: no se persistieron datos de prueba.)")
