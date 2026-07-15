# -*- coding: utf-8 -*-

from datetime import datetime, time, timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'kc_manual_production')
class TestKcOperationalControl(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search([
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.loc_stock = cls.warehouse.lot_stock_id

        cls.line = cls.env['kc.production.line'].create({
            'name': 'QAS Línea Control Operativo',
            'code': 'QASCTL',
            'company_id': cls.company.id,
        })

        mp_categ = cls.company._kc_cmp_resolve_mp_category()
        cls.product_mp = cls.env['product.product'].create({
            'name': 'QAS_MP Control',
            'type': 'consu',
            'is_storable': True,
            'tracking': 'none',
            'standard_price': 5.0,
            'categ_id': mp_categ.id if mp_categ else False,
        })
        cls.product_pt = cls.env['product.product'].create({
            'name': 'QAS_PT Control',
            'type': 'consu',
            'is_storable': True,
            'tracking': 'lot',
            'lot_valuated': True,
            'standard_price': 10.0,
        })

        cls.env['stock.quant'].sudo().with_context(inventory_mode=True).create({
            'product_id': cls.product_mp.id,
            'location_id': cls.loc_stock.id,
            'inventory_quantity': 1000.0,
        }).action_apply_inventory()

        cls.group_bodega = cls.env.ref('kc_manual_production.kc_production_group_bodega')
        cls.group_manager = cls.env.ref('kc_manual_production.kc_production_group_manager')
        cls.user_bodega = cls.env['res.users'].create({
            'name': 'QAS Bodega Control',
            'login': 'qas_kc_bodega_control@test.local',
            'company_id': cls.company.id,
            'company_ids': [(6, 0, [cls.company.id])],
            'groups_id': [(6, 0, [cls.group_bodega.id])],
        })
        cls.user_operador = cls.env['res.users'].create({
            'name': 'QAS Operador Control',
            'login': 'qas_kc_operador_control@test.local',
            'company_id': cls.company.id,
            'company_ids': [(6, 0, [cls.company.id])],
            'groups_id': [(6, 0, [
                cls.env.ref('kc_manual_production.kc_production_group_user').id,
            ])],
        })
        cls.line.write({'user_ids': [(4, cls.user_operador.id)]})

    def _create_daily_cmp(self, consumption_date, state='draft'):
        Consumption = self.env['kc.production.consumption'].with_context(
            kc_pin_authorized=True)
        cmp = Consumption.create({
            'consumption_mode': 'daily',
            'production_line_id': self.line.id,
            'consumption_date': consumption_date,
            'company_id': self.company.id,
            'warehouse_id': self.warehouse.id,
            'line_ids': [(0, 0, {
                'line_type': 'material',
                'product_id': self.product_mp.id,
                'qty': 1.0,
            })],
        })
        if state == 'confirmed':
            cmp.action_confirm()
        elif state == 'done':
            cmp.action_confirm()
            cmp.action_validate()
        return cmp

    def _create_rp_done(self, production_date):
        Entry = self.env['kc.production.entry'].with_context(
            kc_pin_authorized=True)
        entry = Entry.create({
            'production_line_id': self.line.id,
            'company_id': self.company.id,
            'warehouse_id': self.warehouse.id,
            'date_production': datetime.combine(production_date, time(10, 0)),
            'line_ids': [(0, 0, {
                'product_id': self.product_pt.id,
                'qty': 5.0,
                'kc_unit_cost': 10.0,
            })],
        })
        entry.action_confirm()
        entry.action_validate()
        return entry

    def test_qas01_create_daily_cmp(self):
        today = fields.Date.context_today(self.env.user)
        cmp = self._create_daily_cmp(today)
        self.assertEqual(cmp.consumption_mode, 'daily')
        self.assertEqual(cmp.production_line_id, self.line)
        self.assertEqual(cmp.consumption_date, today)

    def test_qas02_duplicate_daily_cmp_blocked(self):
        day = fields.Date.context_today(self.env.user)
        self._create_daily_cmp(day)
        with self.assertRaises(UserError):
            self._create_daily_cmp(day)

    def test_qas03_open_cmp_blocks_next_day(self):
        day1 = fields.Date.context_today(self.env.user) - timedelta(days=1)
        day2 = fields.Date.context_today(self.env.user)
        self._create_daily_cmp(day1, state='draft')
        with self.assertRaises(UserError):
            self._create_daily_cmp(day2)

    def test_qas04_validate_unblocks_sequence(self):
        day1 = fields.Date.context_today(self.env.user) - timedelta(days=1)
        day2 = fields.Date.context_today(self.env.user)
        cmp1 = self._create_daily_cmp(day1, state='draft')
        cmp1.action_confirm()
        cmp1.action_validate()
        cmp2 = self._create_daily_cmp(day2)
        self.assertTrue(cmp2)

    def test_qas05_dashboard_kpis(self):
        today = fields.Date.context_today(self.env.user)
        self._create_rp_done(today)
        self._create_daily_cmp(today, state='done')
        data = self.env['kc.production.dashboard'].get_dashboard_data(
            fields.Date.to_string(today),
            fields.Date.to_string(today),
            self.line.id,
        )
        self.assertEqual(data['kpis']['lines_closed'], 1)
        self.assertEqual(data['kpis']['lines_total'], 1)
        self.assertEqual(data['kpis']['rp_count'], 1)
        self.assertGreaterEqual(data['kpis']['units_produced'], 5.0)

    def test_qas06_orphan_day_detected(self):
        yesterday = fields.Date.context_today(self.env.user) - timedelta(days=1)
        today = fields.Date.context_today(self.env.user)
        self._create_rp_done(yesterday)
        data = self.env['kc.production.dashboard'].get_dashboard_data(
            fields.Date.to_string(yesterday),
            fields.Date.to_string(today),
            self.line.id,
        )
        self.assertGreaterEqual(data['kpis']['orphan_days_count'], 1)
        alerts = [a for a in data['alerts'] if a['type'] == 'orphan_day']
        self.assertTrue(alerts)

    def test_qas07_operador_cannot_create_daily_cmp(self):
        today = fields.Date.context_today(self.env.user)
        Dashboard = self.env['kc.production.dashboard'].with_user(self.user_operador)
        with self.assertRaises(AccessError):
            Dashboard.action_create_daily_cmp(self.line.id, fields.Date.to_string(today))

    def test_qas08_bodega_can_create_daily_cmp(self):
        today = fields.Date.context_today(self.env.user)
        action = self.env['kc.production.dashboard'].with_user(
            self.user_bodega).action_create_daily_cmp(
            self.line.id, fields.Date.to_string(today))
        self.assertEqual(action['res_model'], 'kc.production.consumption')
        cmp = self.env['kc.production.consumption'].browse(action['res_id'])
        self.assertEqual(cmp.consumption_mode, 'daily')

    def test_qas09_calendar_closed_cell(self):
        today = fields.Date.context_today(self.env.user)
        self._create_daily_cmp(today, state='done')
        week_start = today - timedelta(days=6)
        data = self.env['kc.production.dashboard'].get_dashboard_data(
            fields.Date.to_string(week_start),
            fields.Date.to_string(today),
            self.line.id,
        )
        cal = data['compliance_calendar']
        self.assertTrue(cal)
        today_str = fields.Date.to_string(today)
        row = cal['rows'][0]
        cell = next(c for c in row['cells'] if c['date'] == today_str)
        self.assertEqual(cell['status'], 'closed')

    def test_qas10_operador_sees_only_assigned_line(self):
        other_line = self.env['kc.production.line'].create({
            'name': 'QAS Otra Línea',
            'code': 'QASOTR',
            'company_id': self.company.id,
        })
        today = fields.Date.context_today(self.env.user)
        lines = self.env['kc.production.dashboard'].with_user(
            self.user_operador).get_production_lines()
        line_ids = {l['id'] for l in lines}
        self.assertIn(self.line.id, line_ids)
        self.assertNotIn(other_line.id, line_ids)
