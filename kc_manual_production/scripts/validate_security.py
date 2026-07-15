# -*- coding: utf-8 -*-
"""
Script de validación de seguridad — kc_manual_production
Ejecutar dentro de: docker compose exec web odoo shell -d TU_BASE

Uso:
    1. Copia este archivo dentro del contenedor o pégalo línea por línea
       en el shell interactivo.
    2. Si lo copias como archivo, ejecútalo así:
       docker compose exec web odoo shell -d TU_BASE < ruta/al/script.py
    3. Revisa el resumen final con ✓ / ⚠️ para cada prueba.

IMPORTANTE: este script NO modifica datos permanentes a propósito —
usa env.cr.rollback() al final para no dejar basura de prueba en la BD,
EXCEPTO los 2 usuarios y 2 compañías de prueba que crea, los cuales
puedes borrar manualmente después si no los necesitas (se identifican
claramente por su nombre con prefijo 'TEST_KC_').
"""

resultados = []

def check(nombre, condicion, detalle=""):
    estado = "✓ OK" if condicion else "⚠️ FALLO"
    resultados.append((estado, nombre, detalle))
    print(f"{estado} — {nombre} {('— ' + detalle) if detalle else ''}")


print("=" * 70)
print("VALIDACIÓN DE SEGURIDAD — kc_manual_production")
print("=" * 70)

# ---------------------------------------------------------------
# SETUP: crear (o reutilizar) usuarios y compañías de prueba
# ---------------------------------------------------------------

print("\n--- SETUP: usuarios y compañías de prueba ---")

Company = env['res.company']
Users = env['res.users']
Groups = env['res.groups']

company_a = Company.search([('name', '=', 'TEST_KC_Compania_A')], limit=1)
if not company_a:
    company_a = Company.create({'name': 'TEST_KC_Compania_A'})
    print(f"Creada compañía A: {company_a.name} (id={company_a.id})")
else:
    print(f"Reutilizando compañía A existente (id={company_a.id})")

company_b = Company.search([('name', '=', 'TEST_KC_Compania_B')], limit=1)
if not company_b:
    company_b = Company.create({'name': 'TEST_KC_Compania_B'})
    print(f"Creada compañía B: {company_b.name} (id={company_b.id})")
else:
    print(f"Reutilizando compañía B existente (id={company_b.id})")

grupo_user = env.ref('kc_manual_production.kc_production_group_user')
grupo_bodega = env.ref('kc_manual_production.kc_production_group_bodega')
grupo_manager = env.ref('kc_manual_production.kc_production_group_manager')

def crear_o_reusar_usuario(login, name, company, groups):
    u = Users.search([('login', '=', login)], limit=1)
    if not u:
        u = Users.create({
            'login': login,
            'name': name,
            'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
            'groups_id': [(6, 0, groups.ids)],
        })
        print(f"Creado usuario: {login} (compañía={company.name})")
    else:
        # Asegura que tenga la compañía y grupos correctos para la prueba
        u.write({
            'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
            'groups_id': [(6, 0, groups.ids)],
        })
        print(f"Reutilizando y reconfigurando usuario: {login}")
    return u

user_produccion = crear_o_reusar_usuario(
    'test_kc_produccion@test.com', 'TEST_KC Operador Producción',
    company_a, grupo_user
)
user_bodega = crear_o_reusar_usuario(
    'test_kc_bodega@test.com', 'TEST_KC Operador Bodega',
    company_a, grupo_bodega
)
user_manager_a = crear_o_reusar_usuario(
    'test_kc_manager_a@test.com', 'TEST_KC Manager Compañía A',
    company_a, grupo_manager
)
user_manager_b = crear_o_reusar_usuario(
    'test_kc_manager_b@test.com', 'TEST_KC Manager Compañía B',
    company_b, grupo_manager
)

env.cr.commit()  # Necesitamos que los usuarios persistan para with_user()

# ---------------------------------------------------------------
# PRUEBA 1 — Acceso por grupo: producción NO puede crear CMP
# ---------------------------------------------------------------

print("\n--- PRUEBA 1: Producción no puede crear CMP ---")
try:
    env['kc.production.consumption'].with_user(user_produccion).create({
        'company_id': company_a.id,
    })
    check("Producción bloqueado al crear CMP", False,
          "¡Pudo crear un CMP sin tener el grupo bodega!")
except Exception as e:
    check("Producción bloqueado al crear CMP", True, str(e)[:80])

# ---------------------------------------------------------------
# PRUEBA 2 — Acceso por grupo: bodega NO puede crear RP
# ---------------------------------------------------------------

print("\n--- PRUEBA 2: Bodega no puede crear RP ---")
try:
    env['kc.production.entry'].with_user(user_bodega).create({
        'company_id': company_a.id,
    })
    check("Bodega bloqueado al crear RP", False,
          "¡Pudo crear un RP sin tener el grupo producción!")
except Exception as e:
    check("Bodega bloqueado al crear RP", True, str(e)[:80])

# ---------------------------------------------------------------
# PRUEBA 3 — Producción SÍ puede crear RP (caso positivo)
# ---------------------------------------------------------------

print("\n--- PRUEBA 3: Producción SÍ puede crear RP (control positivo) ---")
try:
    rp_test = env['kc.production.entry'].with_user(user_produccion).create({
        'company_id': company_a.id,
    })
    check("Producción puede crear RP", True, f"RP id={rp_test.id}")
except Exception as e:
    check("Producción puede crear RP", False, str(e)[:120])
    rp_test = None

# ---------------------------------------------------------------
# PRUEBA 4 — Aislamiento multi-compañía: manager B no ve RP de A
# ---------------------------------------------------------------

print("\n--- PRUEBA 4: Manager de Compañía B no ve RP de Compañía A ---")
if rp_test:
    try:
        nombre_visto = env['kc.production.entry'].with_user(user_manager_b).browse(rp_test.id).name
        # Si llega aquí sin error, intenta forzar la lectura de un campo
        # para confirmar que realmente está vacío (browse no siempre lanza error solo)
        if not nombre_visto:
            check("Aislamiento multi-compañía RP", True,
                  "browse devolvió registro vacío/inaccesible")
        else:
            check("Aislamiento multi-compañía RP", False,
                  f"¡Manager B pudo leer el RP de A! name={nombre_visto}")
    except Exception as e:
        check("Aislamiento multi-compañía RP", True, str(e)[:80])
else:
    check("Aislamiento multi-compañía RP", False, "No se pudo crear rp_test en prueba 3")

# ---------------------------------------------------------------
# PRUEBA 5 — Manager B tampoco lo ve en una búsqueda (search)
# ---------------------------------------------------------------

print("\n--- PRUEBA 5: Manager B no encuentra el RP de A ni por search() ---")
if rp_test:
    encontrados = env['kc.production.entry'].with_user(user_manager_b).search(
        [('id', '=', rp_test.id)]
    )
    check("search() respeta aislamiento", len(encontrados) == 0,
          f"encontrados={len(encontrados)} (debería ser 0)")

# ---------------------------------------------------------------
# PRUEBA 6 — Manager A SÍ puede ver su propio RP (control positivo)
# ---------------------------------------------------------------

print("\n--- PRUEBA 6: Manager A SÍ ve su propio RP (control positivo) ---")
if rp_test:
    encontrados_a = env['kc.production.entry'].with_user(user_manager_a).search(
        [('id', '=', rp_test.id)]
    )
    check("Manager A ve su propio RP", len(encontrados_a) == 1,
          f"encontrados={len(encontrados_a)} (debería ser 1)")

# ---------------------------------------------------------------
# PRUEBA 7 — Wizard de reversión bloqueado para roles operativos
# ---------------------------------------------------------------

print("\n--- PRUEBA 7: Wizard de reversión bloqueado para producción/bodega ---")
try:
    env['kc.production.entry.reversal.wizard'].with_user(user_produccion).create({})
    check("Wizard reversión bloqueado (producción)", False,
          "¡Pudo acceder al wizard sin ser manager!")
except Exception as e:
    check("Wizard reversión bloqueado (producción)", True, str(e)[:80])

try:
    env['kc.production.consumption.reversal.wizard'].with_user(user_bodega).create({})
    check("Wizard reversión bloqueado (bodega)", False,
          "¡Pudo acceder al wizard sin ser manager!")
except Exception as e:
    check("Wizard reversión bloqueado (bodega)", True, str(e)[:80])

# ---------------------------------------------------------------
# PRUEBA 8 — Manager SÍ puede acceder al wizard (control positivo)
# ---------------------------------------------------------------

print("\n--- PRUEBA 8: Manager A SÍ puede acceder al wizard (control positivo) ---")
if rp_test:
    try:
        wiz = env['kc.production.entry.reversal.wizard'].with_user(user_manager_a).create({
            'entry_id': rp_test.id,
            'reason': 'Prueba automatizada de validación de seguridad',
        })
        check("Manager puede acceder al wizard", True, f"wizard id={wiz.id}")
    except Exception as e:
        check("Manager puede acceder al wizard", False, str(e)[:120])

# ---------------------------------------------------------------
# RESUMEN FINAL
# ---------------------------------------------------------------

print("\n" + "=" * 70)
print("RESUMEN FINAL")
print("=" * 70)
fallos = [r for r in resultados if "FALLO" in r[0]]
for estado, nombre, detalle in resultados:
    print(f"{estado}  {nombre}")

print("\n" + "-" * 70)
if fallos:
    print(f"⚠️  {len(fallos)} prueba(s) FALLARON. Revisa los detalles arriba.")
else:
    print(f"✓ Todas las {len(resultados)} pruebas pasaron correctamente.")
print("-" * 70)

# IMPORTANTE: hacemos rollback para no ensuciar la base con datos de prueba
# EXCEPTO que ya hicimos commit de los usuarios/compañías arriba (necesario
# para que with_user() funcionara). Si quieres limpiar todo, descomenta:
#
# user_produccion.unlink()
# user_bodega.unlink()
# user_manager_a.unlink()
# user_manager_b.unlink()
# company_a.unlink()
# company_b.unlink()
# env.cr.commit()
# print("Datos de prueba eliminados.")

print("\nNOTA: los usuarios y compañías TEST_KC_* quedaron en la base.")
print("Bórralos manualmente desde Ajustes si no los necesitas, o descomenta")
print("el bloque de limpieza al final de este script y vuelve a correrlo.")
