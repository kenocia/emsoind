# -*- coding: utf-8 -*-

from markupsafe import Markup, escape

from odoo import api, fields, models, _

# Severidad -> (clase css, icono FontAwesome)
_SEVERITY = {
    'danger': ('o_fa--danger', 'fa-exclamation-circle'),
    'warning': ('o_fa--warning', 'fa-exclamation-triangle'),
    'info': ('o_fa--info', 'fa-info-circle'),
    'success': ('o_fa--success', 'fa-check-circle'),
}


class SequenceAlertsWizard(models.TransientModel):
    _name = 'kc_fiscal_hn.wizard.sequence_alerts'
    _description = 'Wizard de Alertas de Secuencias Fiscales'

    summary_html = fields.Html(
        string='Resumen',
        readonly=True,
        sanitize=False,
    )
    expired_sequences = fields.Html(
        string='Secuencias Agotadas',
        readonly=True,
        sanitize=False,
    )
    expiring_cais = fields.Html(
        string='CAI Próximos a Vencer',
        readonly=True,
        sanitize=False,
    )
    validation_errors = fields.Html(
        string='Errores de Validación',
        readonly=True,
        sanitize=False,
    )
    journals_incomplete = fields.Html(
        string='Diarios sin configuración SAR',
        readonly=True,
        sanitize=False,
    )

    # ──────────────────────────────────────────────────────────────
    # Carga / refresco
    # ──────────────────────────────────────────────────────────────
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        alerts = self._collect_alerts()
        res.update(self._render_all(alerts))
        return res

    def action_check_sequences(self):
        """Verificar todas las secuencias fiscales (refresca el tablero)."""
        self.ensure_one()
        self.write(self._render_all(self._collect_alerts()))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'kc_fiscal_hn.wizard.sequence_alerts',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _render_all(self, alerts):
        return {
            'expired_sequences': self._format_expired_sequences(alerts['expired']),
            'expiring_cais': self._format_expiring_cais(alerts['expiring']),
            'validation_errors': self._format_validation_errors(alerts['validation']),
            'journals_incomplete': self._format_journals_incomplete(alerts['journals']),
            'summary_html': self._format_summary(alerts),
        }

    # ──────────────────────────────────────────────────────────────
    # Recolección de datos
    # ──────────────────────────────────────────────────────────────
    @api.model
    def _collect_journal_config_issues(self):
        return self.env['account.journal'].search([
            ('type', 'in', ['sale', 'purchase']),
            ('company_id', 'in', self.env.companies.ids),
            ('fiscal_config_state', '!=', 'ok'),
        ], order='type, name')

    @api.model
    def _collect_alerts(self):
        """Recopila alertas de todas las secuencias fiscales."""
        sequences = self.env['ir.sequence'].search([('is_fiscal', '=', True)])
        expired_info = []
        expiring_info = []
        validation_errors = []

        for sequence in sequences:
            expired_info.extend(sequence.check_sequence_expiration())
            for date_range in sequence.date_range_ids:
                expiring_data = date_range.check_cai_expiration()
                if expiring_data:
                    expiring_info.append(expiring_data)
            if sequence.fiscal_validation_error:
                validation_errors.append({
                    'sequence': sequence.name,
                    'error': sequence.fiscal_validation_error,
                })

        return {
            'expired': expired_info,
            'expiring': expiring_info,
            'validation': validation_errors,
            'journals': self._collect_journal_config_issues(),
        }

    # ──────────────────────────────────────────────────────────────
    # Helpers de presentación (HTML)
    # ──────────────────────────────────────────────────────────────
    def _item(self, severity, title, badge, meta_lines):
        cls, icon = _SEVERITY.get(severity, _SEVERITY['info'])
        meta = Markup('').join(
            Markup('<div class="o_fa_meta">%s</div>') % m
            for m in meta_lines if m
        )
        badge_html = (
            Markup('<span class="o_fa_badge">%s</span>') % escape(badge)
            if badge else Markup('')
        )
        return Markup(
            '<div class="o_fa_item %s">'
            '<span class="o_fa_item_icon"><i class="fa %s" role="img"/></span>'
            '<div class="o_fa_item_body">'
            '<div class="o_fa_item_head">'
            '<span class="o_fa_item_title">%s</span>%s</div>%s'
            '</div></div>'
        ) % (cls, icon, escape(title), badge_html, meta)

    def _meta(self, label, value):
        return Markup(
            '<span class="o_fa_meta_label">%s</span> %s'
        ) % (escape(label), escape(str(value)))

    def _empty(self, message):
        return Markup(
            '<div class="o_fa_empty">'
            '<i class="fa fa-check-circle" role="img"/>'
            '<span>%s</span></div>'
        ) % escape(message)

    def _wrap(self, items):
        return Markup('<div class="o_fa_list">%s</div>') % Markup('').join(items)

    # ──────────────────────────────────────────────────────────────
    # Formato por sección
    # ──────────────────────────────────────────────────────────────
    def _format_summary(self, alerts):
        n_exp = len(alerts['expired'])
        n_venc = len(alerts['expiring'])
        n_err = len(alerts['validation'])
        n_diarios = len(alerts['journals'])
        total = n_exp + n_venc + n_err + n_diarios

        if total == 0:
            banner = Markup(
                '<div class="o_fa_banner o_fa_banner--ok">'
                '<i class="fa fa-shield" role="img"/>'
                '<span>Todo en orden — sin alertas fiscales activas.</span>'
                '</div>'
            )
        else:
            banner = Markup(
                '<div class="o_fa_banner o_fa_banner--alert">'
                '<i class="fa fa-bell" role="img"/>'
                '<span>%s incidencia(s) requieren tu atención.</span>'
                '</div>'
            ) % total

        chips = Markup('').join([
            self._chip('Agotadas', n_exp, 'danger', 'fa-hourglass-end'),
            self._chip('CAI por vencer', n_venc, 'warning', 'fa-calendar-times-o'),
            self._chip('Validación', n_err, 'info', 'fa-clipboard'),
            self._chip('Diarios', n_diarios, 'journals', 'fa-book'),
        ])
        return banner + Markup('<div class="o_fa_chips">%s</div>') % chips

    def _chip(self, label, count, tone, icon):
        active = 'o_fa_chip--active' if count else ''
        return Markup(
            '<span class="o_fa_chip o_fa_chip--%s %s">'
            '<i class="fa %s" role="img"/>'
            '<span class="o_fa_chip_label">%s</span>'
            '<span class="o_fa_chip_count">%s</span></span>'
        ) % (tone, active, icon, escape(label), count)

    def _format_expired_sequences(self, expired_data):
        if not expired_data:
            return self._empty(_('Sin secuencias agotadas ni con correlativos bajos.'))
        items = []
        for d in expired_data:
            agotada = d.get('exhausted')
            items.append(self._item(
                'danger' if agotada else 'warning',
                d['sequence'],
                _('AGOTADA') if agotada else _('Próxima a agotarse'),
                [
                    self._meta(_('Restantes:'), d['remaining']),
                    self._meta(_('Período:'), d['date_range']),
                    self._meta(_('CAI:'), d['cai'] or '—'),
                ],
            ))
        return self._wrap(items)

    def _format_expiring_cais(self, expiring_data):
        if not expiring_data:
            return self._empty(_('Ningún CAI próximo a vencer.'))
        items = []
        for d in expiring_data:
            if d.get('expired'):
                sev, badge = 'danger', _('VENCIDO')
            elif d['days_to_expire'] == 0:
                sev, badge = 'danger', _('Vence hoy')
            else:
                sev = 'warning'
                badge = _('%(days)s día(s)', days=d['days_to_expire'])
            items.append(self._item(sev, d['sequence'], badge, [
                self._meta(_('Fecha límite:'), d['expiration_date']),
                self._meta(_('Período:'), d['date_range']),
                self._meta(_('CAI:'), d['cai'] or '—'),
            ]))
        return self._wrap(items)

    def _format_validation_errors(self, errors):
        if not errors:
            return self._empty(_('Sin errores de validación.'))
        items = [
            self._item('info', e['sequence'], _('Revisar'), [Markup('%s') % escape(e['error'])])
            for e in errors
        ]
        return self._wrap(items)

    def _format_journals_incomplete(self, journals):
        if not journals:
            return self._empty(_('Todos los diarios de venta/compra están configurados.'))
        labels = dict(
            self.env['account.journal']._fields['fiscal_config_state'].selection,
        )
        sev_map = {
            'no_seq': 'danger', 'seq_critical': 'danger',
            'no_doc': 'warning', 'seq_alert': 'warning',
        }
        items = []
        for j in journals:
            estado = labels.get(j.fiscal_config_state, j.fiscal_config_state)
            seq = j.fiscal_sequence_id.name if j.fiscal_sequence_id else _('Sin secuencia')
            items.append(self._item(
                sev_map.get(j.fiscal_config_state, 'info'),
                j.display_name,
                estado,
                [
                    self._meta(_('Documento:'), j.document_fiscal or _('N/A')),
                    self._meta(_('Secuencia:'), seq),
                ],
            ))
        return self._wrap(items)

    # ──────────────────────────────────────────────────────────────
    # Acciones
    # ──────────────────────────────────────────────────────────────
    def action_open_incomplete_journals(self):
        return self.env['account.journal'].action_open_fiscal_journals_incomplete()

    def action_validate_all_sequences(self):
        sequences = self.env['ir.sequence'].search([('is_fiscal', '=', True)])
        validated_count = 0
        error_count = 0
        for sequence in sequences:
            try:
                sequence.validate_fiscal_sequence_complete()
                validated_count += 1
            except Exception:
                error_count += 1

        message = _(
            'Validación completada:\n'
            '• Secuencias validadas: %(ok)s\n'
            '• Errores encontrados: %(err)s',
            ok=validated_count,
            err=error_count,
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Validación Completada'),
                'message': message,
                'type': 'success' if error_count == 0 else 'warning',
            },
        }
