# -*- coding: utf-8 -*-
"""QAS Control Operativo — kc_manual_production (CMP diario + dashboard).

Ejecutar en EMSOIND_PRUEBA (o la base deseada):

    sudo systemctl stop odoo.service
    sudo -u odoo /opt/odoo/venv/bin/python3 /opt/odoo/src/community/odoo-bin \\
        shell -c /etc/odoo.conf -d EMSOIND_PRUEBA \\
        < /opt/odoo/src/custom/kc_manual_production/scripts/run_qas_operational_control.py
    sudo systemctl start odoo.service

Los registros de prueba usan prefijo QAS_KC_ y se eliminan al final.
"""
import json
import traceback
from datetime import datetime, time, timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError

RESULTS = []
MARKER = 'QAS_KC_'


def log(case, status, detail=''):
    RESULTS.append({'case': case, 'status': status, 'detail': detail})
    mark = 'PASS' if status == 'PASS' else 'FAIL'
    print(f'[{mark}] {case}: {detail}')


def force_remove_cmps(cmps):
    for cmp in cmps.sorted(lambda c: c.id, reverse=True):
        try:
            if cmp.state == 'done':
                cmp.sudo().write({'state': 'cancel'})
            elif cmp.state == 'confirmed':
                cmp.sudo().write({'state': 'draft'})
            if cmp.state != 'cancel':
                cmp.sudo().action_cancel()
        except Exception:
            pass
        try:
            cmp.sudo().unlink()
        except Exception as exc:
            log('CLEANUP', 'FAIL', f'No se pudo borrar {cmp.display_name}: {exc}')


def cleanup_qas(env):
    Consumption = env['kc.production.consumption']
    Entry = env['kc.production.entry']
    Line = env['kc.production.line']
    Product = env['product.product']
    Users = env['res.users']

    qas_lines = Line.search([('code', 'like', 'QASKC%')])
    if qas_lines:
        force_remove_cmps(Consumption.search([
            ('production_line_id', 'in', qas_lines.ids),
        ]))
        for entry in Entry.search([('production_line_id', 'in', qas_lines.ids)]):
            try:
                entry.sudo().unlink()
            except Exception:
                log('CLEANUP', 'FAIL', f'RP residual: {entry.display_name}')

    force_remove_cmps(Consumption.search([('notes', 'ilike', MARKER)]))

    for entry in Entry.search([('notes', 'ilike', MARKER)]):
        try:
            entry.sudo().unlink()
        except Exception:
            log('CLEANUP', 'FAIL', f'RP residual: {entry.display_name}')

    qas_lines.unlink()
    Product.search([('default_code', 'like', 'QASKC%')]).unlink()
    Users.search([('login', 'like', 'qas_kc_%@test.local')]).unlink()


def setup_qas(env):
    company = env.company
    warehouse = env['stock.warehouse'].search([
        ('company_id', '=', company.id),
    ], limit=1)
    loc = warehouse.lot_stock_id

    line = env['kc.production.line'].create({
        'name': f'{MARKER}Línea Control',
        'code': 'QASKCCTL',
        'company_id': company.id,
    })

    product_mp = env['product.product'].create({
        'name': f'{MARKER}Materia Prima',
        'default_code': 'QASKCMP',
        'type': 'consu',
        'is_storable': True,
        'tracking': 'none',
        'standard_price': 3.0,
    })
    product_pt = env['product.product'].create({
        'name': f'{MARKER}Producto Terminado',
        'default_code': 'QASKCPT',
        'type': 'consu',
        'is_storable': True,
        'tracking': 'lot',
        'lot_valuated': True,
        'standard_price': 12.0,
    })

    env['stock.quant'].sudo().with_context(inventory_mode=True).create({
        'product_id': product_mp.id,
        'location_id': loc.id,
        'inventory_quantity': 500.0,
    }).action_apply_inventory()

    group_bodega = env.ref('kc_manual_production.kc_production_group_bodega')
    group_user = env.ref('kc_manual_production.kc_production_group_user')

    user_bodega = env['res.users'].search([
        ('login', '=', 'qas_kc_bodega@test.local'),
    ], limit=1)
    if not user_bodega:
        user_bodega = env['res.users'].create({
            'name': f'{MARKER}Bodega',
            'login': 'qas_kc_bodega@test.local',
            'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
            'groups_id': [(6, 0, [group_bodega.id])],
        })

    user_operador = env['res.users'].search([
        ('login', '=', 'qas_kc_operador@test.local'),
    ], limit=1)
    if not user_operador:
        user_operador = env['res.users'].create({
            'name': f'{MARKER}Operador',
            'login': 'qas_kc_operador@test.local',
            'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
            'groups_id': [(6, 0, [group_user.id])],
        })
    line.write({'user_ids': [(4, user_operador.id)]})

    return {
        'company': company,
        'warehouse': warehouse,
        'line': line,
        'product_mp': product_mp,
        'product_pt': product_pt,
        'user_bodega': user_bodega,
        'user_operador': user_operador,
    }


def cleanup_line_cmps(env, line):
    force_remove_cmps(env['kc.production.consumption'].search([
        ('production_line_id', '=', line.id),
        ('consumption_mode', '=', 'daily'),
    ]))


def cleanup_line_rps(env, line):
    for entry in env['kc.production.entry'].search([
        ('production_line_id', '=', line.id),
        ('notes', 'ilike', MARKER),
    ]):
        try:
            entry.sudo().unlink()
        except Exception:
            pass


def create_daily_cmp(env, cfg, consumption_date, state='draft'):
    Consumption = env['kc.production.consumption'].with_context(
        kc_pin_authorized=True)
    cmp = Consumption.create({
        'consumption_mode': 'daily',
        'production_line_id': cfg['line'].id,
        'consumption_date': consumption_date,
        'company_id': cfg['company'].id,
        'warehouse_id': cfg['warehouse'].id,
        'notes': f'{MARKER}CMP {consumption_date}',
        'line_ids': [(0, 0, {
            'line_type': 'material',
            'product_id': cfg['product_mp'].id,
            'qty': 2.0,
        })],
    })
    if state in ('confirmed', 'done'):
        cmp.action_confirm()
    if state == 'done':
        cmp.action_validate()
    return cmp


def create_rp_done(env, cfg, production_date):
    Entry = env['kc.production.entry'].with_context(kc_pin_authorized=True)
    entry = Entry.create({
        'production_line_id': cfg['line'].id,
        'company_id': cfg['company'].id,
        'warehouse_id': cfg['warehouse'].id,
        'date_production': datetime.combine(production_date, time(9, 0)),
        'notes': f'{MARKER}RP {production_date}',
        'line_ids': [(0, 0, {
            'product_id': cfg['product_pt'].id,
            'qty': 3.0,
            'kc_unit_cost': 12.0,
        })],
    })
    entry.action_confirm()
    entry.action_validate()
    return entry


def run_qas(env):
    print('=' * 72)
    print('QAS CONTROL OPERATIVO — kc_manual_production')
    print('=' * 72)

    cleanup_qas(env)
    cfg = setup_qas(env)

    today = fields.Date.context_today(env['kc.production.consumption'])
    yesterday = today - timedelta(days=1)
    Dashboard = env['kc.production.dashboard']
    line_id = cfg['line'].id

    # QAS-01 Crear CMP diario
    try:
        cmp = create_daily_cmp(env, cfg, today, state='draft')
        ok = cmp.consumption_mode == 'daily' and cmp.production_line_id == cfg['line']
        log('QAS-01 Crear CMP diario', 'PASS' if ok else 'FAIL', cmp.display_name)
        cmp.unlink()
    except Exception as e:
        log('QAS-01 Crear CMP diario', 'FAIL', str(e))

    # QAS-02 Duplicado bloqueado
    try:
        create_daily_cmp(env, cfg, today, state='draft')
        try:
            create_daily_cmp(env, cfg, today, state='draft')
            log('QAS-02 Duplicado CMP diario', 'FAIL', 'No bloqueó duplicado')
        except UserError as e:
            log('QAS-02 Duplicado CMP diario', 'PASS', str(e)[:120])
        cleanup_line_cmps(env, cfg['line'])
    except Exception as e:
        log('QAS-02 Duplicado CMP diario', 'FAIL', traceback.format_exc()[-300:])

    # QAS-03 CMP abierto bloquea día siguiente
    try:
        create_daily_cmp(env, cfg, yesterday, state='draft')
        try:
            create_daily_cmp(env, cfg, today, state='draft')
            log('QAS-03 Bloqueo secuencia', 'FAIL', 'Permitió crear con ayer abierto')
        except UserError as e:
            log('QAS-03 Bloqueo secuencia', 'PASS', str(e)[:120])
        cleanup_line_cmps(env, cfg['line'])
    except Exception as e:
        log('QAS-03 Bloqueo secuencia', 'FAIL', traceback.format_exc()[-300:])

    # QAS-04 Validar desbloquea
    try:
        cmp_y = create_daily_cmp(env, cfg, yesterday, state='draft')
        cmp_y.action_confirm()
        cmp_y.action_validate()
        cmp_t = create_daily_cmp(env, cfg, today, state='draft')
        log('QAS-04 Validar desbloquea', 'PASS', cmp_t.display_name)
        cleanup_line_cmps(env, cfg['line'])
    except Exception as e:
        log('QAS-04 Validar desbloquea', 'FAIL', traceback.format_exc()[-300:])

    # QAS-05 Dashboard KPIs
    try:
        cleanup_line_cmps(env, cfg['line'])
        cleanup_line_rps(env, cfg['line'])
        create_rp_done(env, cfg, today)
        create_daily_cmp(env, cfg, today, state='done')
        data = Dashboard.get_dashboard_data(
            fields.Date.to_string(today),
            fields.Date.to_string(today),
            line_id,
        )
        ok = (
            data['kpis']['lines_closed'] == 1
            and data['kpis']['rp_count'] >= 1
            and data['kpis']['units_produced'] >= 3
        )
        log('QAS-05 Dashboard KPIs', 'PASS' if ok else 'FAIL',
            f"cerradas={data['kpis']['lines_closed']}, rp={data['kpis']['rp_count']}")
        cleanup_line_cmps(env, cfg['line'])
        cleanup_line_rps(env, cfg['line'])
    except Exception as e:
        log('QAS-05 Dashboard KPIs', 'FAIL', traceback.format_exc()[-300:])

    # QAS-06 Día huérfano
    try:
        cleanup_line_cmps(env, cfg['line'])
        cleanup_line_rps(env, cfg['line'])
        create_rp_done(env, cfg, yesterday)
        data = Dashboard.get_dashboard_data(
            fields.Date.to_string(yesterday),
            fields.Date.to_string(today),
            line_id,
        )
        ok = data['kpis']['orphan_days_count'] >= 1
        log('QAS-06 Día huérfano', 'PASS' if ok else 'FAIL',
            f"huérfanos={data['kpis']['orphan_days_count']}")
        cleanup_line_rps(env, cfg['line'])
    except Exception as e:
        log('QAS-06 Día huérfano', 'FAIL', traceback.format_exc()[-300:])

    # QAS-07 Operador no crea CMP
    try:
        Dashboard.with_user(cfg['user_operador']).action_create_daily_cmp(
            line_id, fields.Date.to_string(today))
        log('QAS-07 Operador bloqueado', 'FAIL', 'Creó CMP sin permiso')
    except AccessError as e:
        log('QAS-07 Operador bloqueado', 'PASS', str(e)[:120])
    except Exception as e:
        log('QAS-07 Operador bloqueado', 'FAIL', str(e)[:120])

    # QAS-08 Bodega crea CMP vía dashboard
    try:
        cleanup_line_cmps(env, cfg['line'])
        action = Dashboard.with_user(cfg['user_bodega']).action_create_daily_cmp(
            line_id, fields.Date.to_string(today))
        cmp = env['kc.production.consumption'].browse(action['res_id'])
        ok = cmp.consumption_mode == 'daily'
        log('QAS-08 Bodega crea CMP', 'PASS' if ok else 'FAIL', cmp.display_name)
        cmp.unlink()
    except Exception as e:
        log('QAS-08 Bodega crea CMP', 'FAIL', traceback.format_exc()[-300:])

    # QAS-09 Calendario celda cerrada
    try:
        cleanup_line_cmps(env, cfg['line'])
        create_daily_cmp(env, cfg, today, state='done')
        week_start = today - timedelta(days=6)
        data = Dashboard.get_dashboard_data(
            fields.Date.to_string(week_start),
            fields.Date.to_string(today),
            line_id,
        )
        cal = data.get('compliance_calendar') or {}
        today_str = fields.Date.to_string(today)
        cell = None
        for row in cal.get('rows', []):
            for c in row.get('cells', []):
                if c.get('date') == today_str:
                    cell = c
                    break
        ok = cell and cell.get('status') == 'closed'
        log('QAS-09 Calendario cerrado', 'PASS' if ok else 'FAIL',
            f"status={cell.get('status') if cell else 'N/A'}")
        cleanup_line_cmps(env, cfg['line'])
    except Exception as e:
        log('QAS-09 Calendario cerrado', 'FAIL', traceback.format_exc()[-300:])

    # QAS-10 Operador solo ve su línea
    try:
        other = env['kc.production.line'].create({
            'name': f'{MARKER}Otra línea',
            'code': 'QASKCOTR',
            'company_id': cfg['company'].id,
        })
        lines = Dashboard.with_user(cfg['user_operador']).get_production_lines()
        ids = {l['id'] for l in lines}
        ok = line_id in ids and other.id not in ids
        log('QAS-10 Filtro operador', 'PASS' if ok else 'FAIL', f'lines={ids}')
        other.unlink()
    except Exception as e:
        log('QAS-10 Filtro operador', 'FAIL', str(e)[:120])

    cleanup_qas(env)
    passed = sum(1 for r in RESULTS if r['status'] == 'PASS')
    print('\n=== RESUMEN QAS ===')
    print(json.dumps(RESULTS, indent=2, ensure_ascii=False))
    print(f'TOTAL: {passed}/{len(RESULTS)} PASS')
    env.cr.rollback()
    print('\nTransacción revertida: no quedan registros QAS en la base.')
    return RESULTS


run_qas(env)
