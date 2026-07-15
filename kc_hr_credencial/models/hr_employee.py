# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

SEQ_CODE = 'kc_hr.employee.credencial'


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    id_credencial = fields.Char(
        string='ID de Credencial',
        copy=False,
        readonly=True,
        tracking=True,
        help='Identificador único del empleado, asignado automáticamente '
             '(formato EMP-0000). Se sincroniza al campo "Referencia" del '
             'contacto asociado y tiene prioridad sobre la numeración fiscal '
             'de contactos.',
    )

    _sql_constraints = [
        ('id_credencial_uniq', 'unique(id_credencial)',
         'El ID de credencial ya está asignado a otro empleado; debe ser único.'),
    ]

    @api.constrains('id_credencial')
    def _check_id_credencial(self):
        for empleado in self:
            cred = (empleado.id_credencial or '').strip()
            if not cred:
                continue
            # Unicidad (insensible a mayúsculas/espacios) entre empleados,
            # incluyendo archivados, como respaldo de la restricción SQL.
            duplicado = self.with_context(active_test=False).search([
                ('id', '!=', empleado.id),
                ('id_credencial', '=ilike', cred),
            ], limit=1)
            if duplicado:
                raise ValidationError(_(
                    'El ID de credencial "%(cred)s" ya está asignado al '
                    'empleado "%(nombre)s". Debe ser único.',
                    cred=empleado.id_credencial,
                    nombre=duplicado.display_name,
                ))
            # Evitar choque con la referencia de un contacto que no sea el suyo.
            contacto_dup = self.env['res.partner'].with_context(
                active_test=False
            ).search([
                ('ref', '=ilike', cred),
                ('id', '!=', empleado.work_contact_id.id or 0),
            ], limit=1)
            if contacto_dup:
                raise ValidationError(_(
                    'El ID de credencial "%(cred)s" ya está usado como '
                    'referencia del contacto "%(nombre)s". Elija otro.',
                    cred=empleado.id_credencial,
                    nombre=contacto_dup.display_name,
                ))

    def _asignar_credencial(self):
        """Asigna automáticamente la credencial a empleados que no la tengan.

        Toma el siguiente valor de la secuencia y, ante una colisión con otra
        credencial o con la referencia de un contacto, avanza la secuencia hasta
        obtener un valor libre (defensa anti-colisión, máx. 50 intentos).
        """
        Sequence = self.env['ir.sequence'].sudo()
        Partner = self.env['res.partner'].with_context(active_test=False)
        for empleado in self:
            if empleado.id_credencial:
                continue
            nueva = Sequence.next_by_code(SEQ_CODE)
            intentos = 0
            while nueva and intentos < 50 and (
                self.with_context(active_test=False).search_count(
                    [('id_credencial', '=ilike', nueva)]
                )
                or Partner.search_count([('ref', '=ilike', nueva)])
            ):
                nueva = Sequence.next_by_code(SEQ_CODE)
                intentos += 1
            if nueva:
                empleado.id_credencial = nueva

    def _sync_ref_credencial(self):
        """Replica la credencial al campo `ref` del contacto del empleado.

        El empleado tiene prioridad: usa el contexto `skip_partner_ref_fiscal_hn`
        para que la numeración automática de contactos (módulo fiscal, si está
        instalado) no pise la credencial. La clave de contexto es inofensiva si
        el módulo fiscal no está presente.
        """
        for empleado in self:
            contacto = empleado.work_contact_id
            if empleado.id_credencial and contacto and (
                contacto.ref != empleado.id_credencial
            ):
                contacto.with_context(
                    skip_partner_ref_fiscal_hn=True
                ).ref = empleado.id_credencial

    @api.model_create_multi
    def create(self, vals_list):
        # Propaga el contexto para que la creación del contacto de trabajo
        # (hr._create_work_contacts) no consuma un correlativo fiscal de
        # contacto que luego sería sobrescrito por la credencial del empleado.
        self_skip = self.with_context(skip_partner_ref_fiscal_hn=True)
        empleados = super(HrEmployee, self_skip).create(vals_list)
        empleados._asignar_credencial()
        empleados._sync_ref_credencial()
        return empleados

    def write(self, vals):
        res = super().write(vals)
        # Si se (re)vincula un contacto de trabajo, propagar la credencial.
        if 'work_contact_id' in vals:
            self._sync_ref_credencial()
        return res

    def action_generar_credencial(self):
        """Botón: genera la credencial a empleados sin código y la sincroniza
        al contacto. Útil para registros ya existentes sin ID."""
        self._asignar_credencial()
        self._sync_ref_credencial()
        generados = self.filtered(lambda e: e.id_credencial)
        if len(self) == 1:
            mensaje = _(
                'Credencial asignada: %s', self.id_credencial,
            ) if self.id_credencial else _(
                'No se pudo generar la credencial. Verifique la secuencia.'
            )
        else:
            mensaje = _(
                'Se asignó credencial a %(n)d empleado(s).',
                n=len(generados),
            )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Credencial de empleado'),
                'message': mensaje,
                'type': 'success' if generados else 'warning',
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    @api.model
    def _init_credencial(self):
        """Backfill idempotente: asigna credencial a empleados sin ella.

        Se invoca desde los datos del módulo en instalación y actualización.
        """
        pendientes = self.search([('id_credencial', '=', False)])
        pendientes._asignar_credencial()
        pendientes._sync_ref_credencial()
