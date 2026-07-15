# -*- coding: utf-8 -*-

from odoo import api, fields, models


class KcPinAuthorizationRule(models.Model):
    """Regla configurable que decide CUÁNDO se exige el PIN.

    El usuario las administra desde Ajustes: indica el documento (model_id), la
    operación lógica (operation, p. ej. 'validate') y, opcionalmente, un dominio
    para acotar a un sub-tipo (p. ej. recepción vs despacho en inventario).

    El enganche en el código de cada módulo es mínimo: el método objetivo
    (button_validate, action_confirm, ...) llama a `_kc_pin_guard(operation, ...)`
    del mixin, que consulta estas reglas para decidir si abre el diálogo de PIN.
    """
    _name = 'kc.pin.authorization.rule'
    _description = 'Regla de Autorización por PIN'
    _order = 'model_name, operation, id'

    name = fields.Char(
        string='Nombre', compute='_compute_name', store=True, readonly=False,
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía',
        default=lambda self: self.env.company,
    )
    model_id = fields.Many2one(
        'ir.model', string='Documento', required=True, ondelete='cascade',
        help='Modelo sobre el que se exige la autorización por PIN.',
    )
    model_name = fields.Char(
        related='model_id.model', string='Modelo técnico',
        store=True, index=True,
    )
    operation = fields.Selection(
        selection='_selection_operation',
        string='Operación', required=True, default='validate',
        help='Punto de acción que se intercepta. Debe coincidir con la clave '
             'que usa el módulo en su enganche (p. ej. "validate").',
    )
    domain = fields.Char(
        string='Filtro (dominio)', default='[]',
        help='Opcional. Acota la regla a un sub-tipo de operación. '
             'Ej. recepción: [("picking_type_code", "=", "incoming")].',
    )
    reason = fields.Char(
        string='Motivo',
        help='Texto que se muestra en el diálogo y se guarda en el chatter y '
             'en el log de auditoría.',
    )

    @api.model
    def _selection_operation(self):
        """Catálogo base de operaciones. Los módulos-puente pueden ampliarlo
        con `selection_add` en su propia herencia del campo."""
        return [
            ('validate', 'Validar'),
            ('confirm', 'Confirmar'),
            ('post', 'Publicar / Contabilizar'),
            ('reverse', 'Revertir'),
            ('cancel', 'Cancelar'),
            ('done', 'Marcar como hecho'),
        ]

    @api.depends('model_id', 'operation', 'domain')
    def _compute_name(self):
        labels = dict(self._fields['operation']._description_selection(self.env))
        for rule in self:
            model_label = rule.model_id.name or rule.model_name or ''
            op_label = labels.get(rule.operation, rule.operation or '')
            suffix = ' (con filtro)' if rule.domain and rule.domain.strip() not in ('', '[]') else ''
            rule.name = ('%s · %s%s' % (model_label, op_label, suffix)).strip(' ·')

    @api.model
    def _rules_for(self, model_name, operation):
        """Reglas activas que aplican a (modelo, operación) en la(s) compañía(s)
        del usuario."""
        return self.search([
            ('model_name', '=', model_name),
            ('operation', '=', operation),
            '|',
            ('company_id', '=', False),
            ('company_id', 'in', self.env.companies.ids),
        ])
