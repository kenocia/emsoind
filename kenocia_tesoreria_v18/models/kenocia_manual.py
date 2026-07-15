# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3
"""Backend del Manual interactivo de Tesorería KENOCIA.

Provee el estado real de configuración (checklist en vivo) y las alertas
operativas que se muestran en la guía interactiva del módulo.
"""

from datetime import timedelta

from odoo import _, api, fields, models


class KenociaTreasuryManual(models.AbstractModel):
    _name = 'kenocia.treasury.manual'
    _description = 'Manual interactivo de Tesorería KENOCIA'

    # ── Punto de entrada único ──────────────────────────────────────────
    @api.model
    def get_manual_data(self):
        """Devuelve estado de configuración, progreso y alertas."""
        self.check_access('read')
        companies = self.env.companies
        config_groups = self._build_config_groups(companies)
        progress = self._compute_progress(config_groups)
        return {
            'config_groups': config_groups,
            'progress': progress,
            'alerts': self._get_alerts(companies),
            'roles': self._get_roles_summary(),
            'companies': [
                {'id': company.id, 'name': company.name}
                for company in companies
            ],
            'generated_on': fields.Datetime.to_string(fields.Datetime.now()),
        }

    # ── Helpers de entorno ──────────────────────────────────────────────
    def _acc_env(self, companies):
        """Entorno elevado para leer config contable agregada."""
        return self.sudo().with_context(allowed_company_ids=companies.ids).env

    def _names(self, companies):
        return ', '.join(companies.mapped('name'))

    # ── Construcción del checklist ──────────────────────────────────────
    def _build_config_groups(self, companies):
        return [
            self._group_accounts(companies),
            self._group_journals(companies),
            self._group_sequences(companies),
            self._group_petty_cash(companies),
            self._group_fiscal(companies),
            self._group_dispersion(companies),
            self._group_roles(companies),
        ]

    def _item(self, key, title, desc, status, detail='',
              required=False, action=None, fix_label=None, count=None):
        return {
            'key': key,
            'title': title,
            'desc': desc,
            'status': status,
            'detail': detail,
            'required': required,
            'action': action,
            'fix_label': fix_label or _('Configurar'),
            'count': count,
        }

    # 1) Cuentas contables de anticipo
    def _group_accounts(self, companies):
        items = []

        missing_cxc = companies.filtered(
            lambda c: not c.kenocia_advance_account_cxc_id,
        )
        not_recon_cxc = companies.filtered(
            lambda c: c.kenocia_advance_account_cxc_id
            and not c.kenocia_advance_account_cxc_id.reconcile,
        )
        if missing_cxc:
            items.append(self._item(
                'adv_cxc',
                _('Cuenta de anticipos de clientes (CXC)'),
                _('Cuenta de PASIVO donde se registran los cobros por '
                  'adelantado de clientes (ej. 2090101 Anticipos de clientes).'),
                'pending', required=True,
                detail=_('Sin definir en: %s', self._names(missing_cxc)),
                action='kenocia_tesoreria_v18.action_kenocia_advance_accounts',
                fix_label=_('Definir cuenta'),
            ))
        elif not_recon_cxc:
            items.append(self._item(
                'adv_cxc',
                _('Cuenta de anticipos de clientes (CXC)'),
                _('La cuenta debe permitir conciliación para aplicar '
                  'anticipos a las facturas.'),
                'warning', required=True,
                detail=_('Falta "Permitir conciliación" en: %s',
                         self._names(not_recon_cxc)),
                action='kenocia_tesoreria_v18.action_kenocia_advance_accounts',
                fix_label=_('Activar conciliación'),
            ))
        else:
            items.append(self._item(
                'adv_cxc',
                _('Cuenta de anticipos de clientes (CXC)'),
                _('Cuenta de PASIVO conciliable para anticipos de clientes.'),
                'ok', required=True,
                detail=', '.join(
                    f'{c.name}: {c.kenocia_advance_account_cxc_id.display_name}'
                    for c in companies
                ),
                action='kenocia_tesoreria_v18.action_kenocia_advance_accounts',
                fix_label=_('Revisar'),
            ))

        missing_cxp = companies.filtered(
            lambda c: not c.kenocia_advance_account_cxp_id,
        )
        not_recon_cxp = companies.filtered(
            lambda c: c.kenocia_advance_account_cxp_id
            and not c.kenocia_advance_account_cxp_id.reconcile,
        )
        if missing_cxp:
            items.append(self._item(
                'adv_cxp',
                _('Cuenta de anticipos a proveedores (CXP)'),
                _('Cuenta de ACTIVO donde se registran los pagos por '
                  'adelantado a proveedores.'),
                'pending', required=True,
                detail=_('Sin definir en: %s', self._names(missing_cxp)),
                action='kenocia_tesoreria_v18.action_kenocia_advance_accounts',
                fix_label=_('Definir cuenta'),
            ))
        elif not_recon_cxp:
            items.append(self._item(
                'adv_cxp',
                _('Cuenta de anticipos a proveedores (CXP)'),
                _('La cuenta debe permitir conciliación para aplicar '
                  'anticipos a las facturas.'),
                'warning', required=True,
                detail=_('Falta "Permitir conciliación" en: %s',
                         self._names(not_recon_cxp)),
                action='kenocia_tesoreria_v18.action_kenocia_advance_accounts',
                fix_label=_('Activar conciliación'),
            ))
        else:
            items.append(self._item(
                'adv_cxp',
                _('Cuenta de anticipos a proveedores (CXP)'),
                _('Cuenta de ACTIVO conciliable para anticipos a proveedores.'),
                'ok', required=True,
                detail=', '.join(
                    f'{c.name}: {c.kenocia_advance_account_cxp_id.display_name}'
                    for c in companies
                ),
                action='kenocia_tesoreria_v18.action_kenocia_advance_accounts',
                fix_label=_('Revisar'),
            ))

        return {
            'key': 'accounts',
            'title': _('Cuentas contables'),
            'icon': 'fa-book',
            'desc': _('Cuentas de anticipo usadas por los adelantos CXC/CXP.'),
            'items': items,
        }

    # 2) Diarios y métodos de pago
    def _group_journals(self, companies):
        env = self._acc_env(companies)
        Journal = env['account.journal']
        items = []

        bank_journals = Journal.search([
            ('type', '=', 'bank'),
            ('company_id', 'in', companies.ids),
        ])
        items.append(self._item(
            'bank_exists',
            _('Diario(s) de banco'),
            _('Se necesita al menos un diario de tipo Banco para registrar '
              'cobros, pagos y dispersiones.'),
            'ok' if bank_journals else 'pending',
            required=True,
            detail=_('%s diario(s) de banco', len(bank_journals))
            if bank_journals else _('No hay diarios de banco creados.'),
            action='kenocia_tesoreria_v18.action_kenocia_journal_bank_cash',
            fix_label=_('Crear diario'),
            count=len(bank_journals),
        ))

        liquidity = Journal.search([
            ('type', 'in', ('bank', 'cash')),
            ('company_id', 'in', companies.ids),
        ])
        missing_out = liquidity.filtered('kenocia_missing_payment_account')
        items.append(self._item(
            'outstanding',
            _('Cuentas de pagos pendientes (outstanding)'),
            _('Cada método de pago de los diarios de banco/caja debe tener su '
              'cuenta de pagos pendientes; si falta, los pagos pueden quedar '
              'sin asiento contable.'),
            'warning' if missing_out else 'ok',
            required=True,
            detail=_('Falta cuenta outstanding en: %s',
                     ', '.join(missing_out.mapped('name')))
            if missing_out else _('Todos los diarios de liquidez están OK.'),
            action='kenocia_tesoreria_v18.action_kenocia_journal_bank_cash',
            fix_label=_('Revisar diarios'),
            count=len(missing_out),
        ))

        general = Journal.search([
            ('type', '=', 'general'),
            ('company_id', 'in', companies.ids),
        ], limit=1)
        items.append(self._item(
            'general_journal',
            _('Diario misceláneo (general)'),
            _('Necesario para registrar los asientos de aplicación de '
              'anticipos a facturas.'),
            'ok' if general else 'pending',
            required=True,
            detail=general.display_name if general
            else _('No se encontró un diario de tipo general.'),
        ))

        return {
            'key': 'journals',
            'title': _('Diarios y métodos de pago'),
            'icon': 'fa-university',
            'desc': _('Diarios de banco, caja y misceláneo con sus cuentas.'),
            'items': items,
        }

    # 3) Secuencias bancarias (correlativos)
    def _group_sequences(self, companies):
        sequences = self.env['kenocia.sequence'].search([
            ('company_id', 'in', companies.ids),
            ('active', '=', True),
        ])
        items = [self._item(
            'sequences',
            _('Correlativos bancarios'),
            _('Opcional. Define correlativos propios por (diario, tipo) para '
              'cheques, depósitos, transferencias, etc. Si no existen, los '
              'pagos usan la numeración nativa de Odoo (válido).'),
            'ok' if sequences else 'info',
            detail=_('%s secuencia(s) activa(s).', len(sequences))
            if sequences else _('Sin secuencias: se usa numeración nativa.'),
            action='kenocia_tesoreria_v18.action_kenocia_sequence',
            fix_label=_('Gestionar secuencias'),
            count=len(sequences),
        )]
        return {
            'key': 'sequences',
            'title': _('Correlativos bancarios'),
            'icon': 'fa-list-ol',
            'desc': _('Numeración interna de chequera/depósitos/dispersión.'),
            'items': items,
        }

    # 4) Caja chica
    def _group_petty_cash(self, companies):
        funds = self.env['kenocia.petty.cash'].search([
            ('company_id', 'in', companies.ids),
            ('state', 'in', ('draft', 'open')),
        ])
        bad_bridge = funds.filtered(
            lambda f: f.account_bridge_id and not f.account_bridge_id.reconcile,
        )
        items = [self._item(
            'petty_bridge',
            _('Cuenta puente de los fondos'),
            _('Cada fondo de caja chica usa una cuenta puente (tránsito) que '
              'debe permitir conciliación para las recargas en dos pasos.'),
            'warning' if bad_bridge else 'ok',
            detail=_('Falta conciliación en cuentas puente de: %s',
                     ', '.join(bad_bridge.mapped('name')))
            if bad_bridge else (
                _('%s fondo(s) configurados correctamente.', len(funds))
                if funds else _('Aún no hay fondos creados (opcional).')
            ),
            action='kenocia_tesoreria_v18.action_kenocia_petty_cash',
            fix_label=_('Ver fondos'),
            count=len(funds),
        )]
        return {
            'key': 'petty_cash',
            'title': _('Caja chica'),
            'icon': 'fa-money',
            'desc': _('Fondos, cuenta puente y custodios.'),
            'items': items,
        }

    # 5) Cumplimiento fiscal SAR (kc_fiscal_hn_v18)
    def _group_fiscal(self, companies):
        env = self._acc_env(companies)
        items = []

        no_class = companies.filtered(
            lambda c: not c.tipo_contribuyente,
        ) if 'tipo_contribuyente' in companies._fields else companies.browse()
        items.append(self._item(
            'sar_class',
            _('Clasificación de contribuyente SAR'),
            _('Define las obligaciones fiscales (DMC, retención). La '
              'liquidación de caja chica valida el cumplimiento según esta '
              'clasificación.'),
            'pending' if no_class else 'ok',
            detail=_('Sin clasificar: %s', self._names(no_class))
            if no_class else ', '.join(
                f'{c.name}: {dict(c._fields["tipo_contribuyente"].selection).get(c.tipo_contribuyente, "")}'
                for c in companies
                if 'tipo_contribuyente' in c._fields and c.tipo_contribuyente
            ),
        ))

        if 'document_fiscal' in env['account.journal']._fields:
            vendor_journals = env['account.journal'].search([
                ('type', '=', 'purchase'),
                ('document_fiscal', 'in', ('vendors', 'boleta')),
                ('company_id', 'in', companies.ids),
            ])
            items.append(self._item(
                'sar_vendor_journal',
                _('Diario fiscal de compras (FA / Boleta)'),
                _('Necesario para liquidar caja chica con facturas de '
                  'proveedor que cumplen SAR.'),
                'ok' if vendor_journals else 'info',
                detail=_('%s diario(s) fiscal(es) de compra.',
                         len(vendor_journals))
                if vendor_journals else _('No hay diario de compras marcado '
                                          'como FA/Boleta.'),
                count=len(vendor_journals),
            ))

        return {
            'key': 'fiscal',
            'title': _('Cumplimiento fiscal SAR'),
            'icon': 'fa-balance-scale',
            'desc': _('Parámetros SAR usados por la liquidación de caja chica.'),
            'items': items,
        }

    # 6) Dispersión / pagos masivos
    def _group_dispersion(self, companies):
        env = self._acc_env(companies)
        bank_with_format = env['account.journal'].search_count([
            ('type', '=', 'bank'),
            ('kenocia_bank_format', '!=', False),
            ('company_id', 'in', companies.ids),
        ])
        vendors_no_bank = env['res.partner'].search_count([
            ('supplier_rank', '>', 0),
            ('bank_ids', '=', False),
            ('parent_id', '=', False),
            ('company_id', 'in', [False] + companies.ids),
        ])
        items = [
            self._item(
                'bank_format',
                _('Formato de dispersión por banco'),
                _('Para generar el archivo TXT del banco, el diario bancario '
                  'debe tener su formato (BAC, Atlántida, Ficohsa, etc.).'),
                'ok' if bank_with_format else 'info',
                detail=_('%s diario(s) con formato.', bank_with_format)
                if bank_with_format else _('Sin formato configurado (opcional '
                                           'hasta usar dispersión).'),
                action='kenocia_tesoreria_v18.action_kenocia_journal_bank_cash',
                fix_label=_('Configurar diario'),
                count=bank_with_format,
            ),
            self._item(
                'vendor_bank',
                _('Cuentas bancarias de proveedores'),
                _('La dispersión a proveedores requiere que cada proveedor '
                  'tenga su cuenta bancaria registrada.'),
                'info' if vendors_no_bank else 'ok',
                detail=_('%s proveedor(es) sin cuenta bancaria.',
                         vendors_no_bank)
                if vendors_no_bank else _('Proveedores con cuenta bancaria OK.'),
                count=vendors_no_bank,
            ),
        ]
        return {
            'key': 'dispersion',
            'title': _('Dispersión / pagos masivos'),
            'icon': 'fa-random',
            'desc': _('Requisitos para dispersar a proveedores y nómina.'),
            'items': items,
        }

    # 7) Roles y usuarios
    def _group_roles(self, companies):
        groups = [
            ('group_tesoreria_cxc', _('Tesorería CXC')),
            ('group_tesoreria_cxp', _('Tesorería CXP')),
            ('group_tesoreria_supervisor', _('Supervisor de Tesorería')),
            ('group_tesoreria_admin', _('Administrador de Tesorería')),
            ('group_tesoreria_custodian', _('Custodio de Caja Chica')),
        ]
        counts = {}
        for xmlid, _label in groups:
            group = self.env.ref(
                f'kenocia_tesoreria_v18.{xmlid}', raise_if_not_found=False,
            )
            counts[xmlid] = len(group.users) if group else 0

        has_admin = counts.get('group_tesoreria_admin') or counts.get(
            'group_tesoreria_supervisor')
        detail = ' · '.join(
            f'{label}: {counts.get(xmlid, 0)}' for xmlid, label in groups
        )
        items = [self._item(
            'roles',
            _('Roles asignados a usuarios'),
            _('Asigne los roles de Tesorería a los usuarios que operan el '
              'módulo (al menos un Supervisor o Administrador).'),
            'ok' if has_admin else 'warning',
            detail=detail,
            action='base.action_res_users',
            fix_label=_('Gestionar usuarios'),
        )]
        return {
            'key': 'roles',
            'title': _('Roles y usuarios'),
            'icon': 'fa-users',
            'desc': _('Quién puede operar cada parte del módulo.'),
            'items': items,
        }

    # ── Progreso (solo ítems requeridos) ────────────────────────────────
    def _compute_progress(self, config_groups):
        required = [
            item
            for group in config_groups
            for item in group['items']
            if item['required']
        ]
        done = [item for item in required if item['status'] == 'ok']
        total = len(required)
        pending = [
            {'title': item['title'], 'status': item['status']}
            for item in required if item['status'] != 'ok'
        ]
        return {
            'done': len(done),
            'total': total,
            'pct': round(len(done) / total * 100) if total else 100,
            'pending': pending,
        }

    # ── Alertas operativas ──────────────────────────────────────────────
    def _get_alerts(self, companies):
        today = fields.Date.today()
        env = self._acc_env(companies)
        alerts = []

        cxp_due = env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
            ('invoice_date_due', '<=', today),
            ('company_id', 'in', companies.ids),
        ])
        if cxp_due:
            total = sum(cxp_due.mapped('amount_residual'))
            alerts.append({
                'level': 'danger',
                'icon': 'fa-exclamation-triangle',
                'title': _('CXP vencido'),
                'msg': _('%(n)s factura(s) de proveedor vencidas por '
                         'L %(amount)s.', n=len(cxp_due), amount=f'{total:,.0f}'),
                'action': 'kenocia_tesoreria_v18.action_kenocia_payment_cxp',
            })

        cxc_crit = env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
            ('invoice_date_due', '<=', today - timedelta(days=60)),
            ('company_id', 'in', companies.ids),
        ])
        if cxc_crit:
            total = sum(cxc_crit.mapped('amount_residual'))
            alerts.append({
                'level': 'warning',
                'icon': 'fa-clock-o',
                'title': _('CXC crítica (>60 días)'),
                'msg': _('%(n)s factura(s) de clientes con más de 60 días sin '
                         'cobrar por L %(amount)s.',
                         n=len(cxc_crit), amount=f'{total:,.0f}'),
                'action': 'kenocia_tesoreria_v18.action_kenocia_payment_cxc',
            })

        pending = self.env['kenocia.petty.cash.line'].search([
            ('state', '=', 'delivered'),
            ('petty_cash_id.company_id', 'in', companies.ids),
        ])
        if pending:
            total = sum(pending.mapped('amount'))
            alerts.append({
                'level': 'warning',
                'icon': 'fa-file-text-o',
                'title': _('Caja chica sin liquidar'),
                'msg': _('%(n)s anticipo(s) entregado(s) sin factura SAR por '
                         'L %(amount)s.', n=len(pending),
                         amount=f'{total:,.0f}'),
                'action': 'kenocia_tesoreria_v18.action_kenocia_petty_cash',
            })

        transit = self.env['kenocia.petty.cash.recharge'].search([
            ('state', '=', 'in_transit'),
            ('petty_cash_id.company_id', 'in', companies.ids),
        ])
        if transit:
            total = sum(transit.mapped('amount'))
            alerts.append({
                'level': 'info',
                'icon': 'fa-truck',
                'title': _('Recargas en tránsito'),
                'msg': _('%(n)s recarga(s) de caja chica pendientes de '
                         'confirmar el efectivo recibido (L %(amount)s).',
                         n=len(transit), amount=f'{total:,.0f}'),
                'action': 'kenocia_tesoreria_v18.action_kenocia_petty_cash',
            })

        return alerts

    # ── Resumen de roles del usuario actual ─────────────────────────────
    def _get_roles_summary(self):
        user = self.env.user
        return {
            'is_cxc': user.has_group('kenocia_tesoreria_v18.group_tesoreria_cxc'),
            'is_cxp': user.has_group('kenocia_tesoreria_v18.group_tesoreria_cxp'),
            'is_supervisor': user.has_group(
                'kenocia_tesoreria_v18.group_tesoreria_supervisor'),
            'is_admin': user.has_group(
                'kenocia_tesoreria_v18.group_tesoreria_admin'),
            'is_custodian': user.has_group(
                'kenocia_tesoreria_v18.group_tesoreria_custodian'),
        }
