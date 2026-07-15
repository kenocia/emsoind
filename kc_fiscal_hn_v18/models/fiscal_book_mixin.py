# -*- coding: utf-8 -*-

import base64
import logging
from io import BytesIO
from typing import Any

import xlsxwriter
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

BOOK_ESTADO = [
    ('pendiente', 'Pendiente'),
    ('declarado', 'Declarado'),
    ('rectificado', 'Rectificado'),
]

# Campos editables cuando la línea ya está declarada ante el SAR
ALLOWED_WHEN_DECLARED = frozenset({
    'notas_rectificacion',
})

# Campos bloqueados si estado == declarado (fiscales)
FISCAL_LOCKED_WHEN_DECLARED = frozenset({
    'fecha', 'move_id', 'numero_factura', 'cai',
    'rtn_cliente', 'rtn_proveedor', 'cliente', 'proveedor',
    'exento', 'exonerado', 'gravado_15', 'isv_15', 'gravado_18', 'isv_18',
    'descuento', 'total', 'total_factura', 'monto_exonerado',
    'base_imponible', 'tipo_retencion', 'tipo_servicio_retencion',
    'porcentaje_retencion', 'monto_retenido',
    'clase_documento', 'monto_costo', 'monto_gasto', 'monto_no_deducible',
    'numero_constancia_exonerado', 'numero_oc_exenta',
    'periodo_desde', 'periodo_hasta', 'company_id',
})

TRACKED_BOOK_FIELDS = FISCAL_LOCKED_WHEN_DECLARED | ALLOWED_WHEN_DECLARED | frozenset({
    'estado', 'fecha_declaracion', 'declarado_por', 'notas_rectificacion',
})


class FiscalBookMixin(models.AbstractModel):
    """Campos y auditoría comunes para libros fiscales SAR."""

    _name = 'kc.fiscal.book.mixin'
    _description = 'Mixin Libros Fiscales SAR'

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )
    move_id = fields.Many2one(
        'account.move',
        string='Factura origen',
        index=True,
        ondelete='set null',
        copy=False,
    )
    fecha = fields.Date(string='Fecha', required=True, index=True)
    estado = fields.Selection(
        selection=BOOK_ESTADO,
        string='Estado declaración',
        default='pendiente',
        required=True,
        tracking=True,
        index=True,
    )
    fecha_declaracion = fields.Date(
        string='Fecha declaración SAR',
        tracking=True,
        readonly=True,
    )
    declarado_por = fields.Many2one(
        'res.users',
        string='Declarado por',
        tracking=True,
        readonly=True,
    )
    notas_rectificacion = fields.Text(string='Notas de rectificación', tracking=True)
    periodo_desde = fields.Date(string='Período desde', index=True)
    periodo_hasta = fields.Date(string='Período hasta', index=True)
    is_fiscal_locked = fields.Boolean(
        string='Bloqueo fiscal (declarado)',
        compute='_compute_is_fiscal_locked',
        help='Si está declarado, los montos y RTN no se pueden modificar.',
    )

    @api.depends('estado')
    def _compute_is_fiscal_locked(self) -> None:
        for line in self:
            line.is_fiscal_locked = True

    def _get_fiscal_locked_fields(self) -> frozenset:
        return FISCAL_LOCKED_WHEN_DECLARED

    def _check_manual_fiscal_write(self, vals: dict) -> None:
        """Impide editar campos fiscales generados desde facturas."""
        if self.env.context.get('skip_book_line_lock'):
            return
        locked_fields = self._get_fiscal_locked_fields()
        disallowed = set(vals.keys()) & locked_fields
        disallowed -= {'message_follower_ids', 'message_ids', 'activity_ids'}
        if disallowed:
            labels = ', '.join(sorted(disallowed))
            raise UserError(_(
                'Los datos fiscales del libro no se pueden modificar '
                'manualmente.\n\n'
                'Campos bloqueados: %(fields)s.\n\n'
                'Use «Generar Libro» para actualizar desde las '
                'facturas confirmadas.',
                fields=labels,
            ))

    def _check_declared_line_write(self, vals: dict) -> None:
        """Impide modificar campos fiscales en líneas ya declaradas."""
        if self.env.context.get('skip_declared_lock'):
            return
        locked_fields = self._get_fiscal_locked_fields()
        for record in self.filtered(lambda r: r.estado == 'declarado'):
            disallowed = set(vals.keys()) & locked_fields
            if 'estado' in vals:
                if vals.get('estado') == 'rectificado':
                    disallowed.discard('estado')
                elif vals.get('estado') != 'declarado':
                    disallowed.add('estado')
            allowed = ALLOWED_WHEN_DECLARED
            if vals.get('estado') == 'rectificado':
                allowed = allowed | {'estado'}
            disallowed -= allowed
            disallowed -= {'message_follower_ids', 'message_ids', 'activity_ids'}
            if disallowed:
                labels = ', '.join(sorted(disallowed))
                raise UserError(
                    _(
                        'La línea "%(line)s" ya fue declarada ante el SAR. '
                        'No puede modificar: %(fields)s. '
                        'Solo puede actualizar las notas de rectificación, o marcar como rectificado.',
                        line=record.display_name,
                        fields=labels,
                    )
                )

    def _audit_value_display(self, field_name: str, value: Any) -> str:
        if value is False or value is None:
            return ''
        field = self._fields.get(field_name)
        if not field:
            return str(value)
        if field.type == 'many2one':
            return value.display_name if hasattr(value, 'display_name') else str(value)
        if field.type == 'selection':
            return dict(field.selection).get(value, str(value))
        if field.type in ('monetary', 'float'):
            return f'{float(value):.2f}'
        return str(value)

    def _create_book_audit(
        self,
        field_name: str,
        old_value: Any,
        new_value: Any,
        action: str = 'modificacion',
        reason: str | None = None,
    ) -> None:
        self.ensure_one()
        self.env['kc_fiscal_hn.book.audit'].create({
            'res_model': self._name,
            'res_id': self.id,
            'field_name': field_name,
            'old_value': self._audit_value_display(field_name, old_value),
            'new_value': self._audit_value_display(field_name, new_value),
            'action': action,
            'reason': reason or self.notas_rectificacion,
            'user_id': self.env.user.id,
            'company_id': self.company_id.id,
        })

    def write(self, vals: dict):
        if self.env.context.get('skip_book_audit'):
            return super().write(vals)

        self._check_manual_fiscal_write(vals)
        self._check_declared_line_write(vals)

        if vals.get('estado') == 'declarado':
            vals = dict(vals)
            vals.setdefault('fecha_declaracion', fields.Date.context_today(self))
            vals.setdefault('declarado_por', self.env.user.id)

        audit_fields = [f for f in vals if f in TRACKED_BOOK_FIELDS]
        old_map = {}
        if audit_fields:
            for rec in self:
                old_map[rec.id] = {f: rec[f] for f in audit_fields}

        res = super().write(vals)

        action = 'rectificacion' if vals.get('estado') == 'rectificado' else (
            'declaracion' if vals.get('estado') == 'declarado' else 'modificacion'
        )
        for rec in self:
            for field_name in audit_fields:
                old = old_map.get(rec.id, {}).get(field_name)
                new = rec[field_name]
                if old != new:
                    rec._create_book_audit(
                        field_name, old, new,
                        action=action,
                        reason=vals.get('notas_rectificacion'),
                    )
        return res

    def unlink(self):
        if not self.env.context.get('skip_book_line_lock'):
            raise UserError(_(
                'Las líneas del libro no se pueden eliminar '
                'manualmente.\n\n'
                'Regenere el libro para actualizar el contenido.',
            ))
        return super().unlink()

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('skip_book_line_lock'):
            raise UserError(_(
                'Las líneas del libro se crean automáticamente '
                'al pulsar «Generar Libro».',
            ))
        return super().create(vals_list)

    def action_marcar_declarado(self):
        self.write({
            'estado': 'declarado',
            'fecha_declaracion': fields.Date.context_today(self),
            'declarado_por': self.env.user.id,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Declarado'),
                'message': _('Las líneas seleccionadas fueron marcadas como declaradas ante el SAR.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_marcar_rectificado(self):
        self.with_context(skip_declared_lock=True).write({'estado': 'rectificado'})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Rectificado'),
                'message': _(
                    'Estado actualizado a rectificado. '
                    'Regenere el libro si necesita actualizar los datos.',
                ),
                'type': 'warning',
            },
        }

    def action_marcar_pendiente(self):
        self.with_context(skip_declared_lock=True).write({
            'estado': 'pendiente',
            'fecha_declaracion': False,
            'declarado_por': False,
        })

    def _export_book_excel(self, sheet_name: str, headers: list, rows: list) -> dict:
        """Exporta líneas del libro a Excel y devuelve acción de descarga."""
        if not self:
            raise UserError(_('No hay líneas para exportar.'))
        filename = f'{sheet_name}_{fields.Date.context_today(self)}.xlsx'
        stream = BytesIO()
        workbook = xlsxwriter.Workbook(stream, {'in_memory': True})
        sheet = workbook.add_worksheet(sheet_name[:31])
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D9E1F2', 'border': 1})
        money_fmt = workbook.add_format({'num_format': 'L#,##0.00', 'border': 1})
        cell_fmt = workbook.add_format({'border': 1})
        for col, title in enumerate(headers):
            sheet.write(0, col, title, header_fmt)
        for row_idx, row in enumerate(rows, start=1):
            for col_idx, cell in enumerate(row):
                if isinstance(cell, (int, float)) and col_idx >= 4:
                    sheet.write(row_idx, col_idx, cell, money_fmt)
                else:
                    sheet.write(row_idx, col_idx, cell, cell_fmt)
        sheet.freeze_panes(1, 0)
        if rows:
            sheet.autofilter(0, 0, len(rows), len(headers) - 1)
        workbook.close()
        att = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(stream.getvalue()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name,
            'res_id': self[:1].id if len(self) == 1 else 0,
        })
        stream.close()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{att.id}?download=true',
            'target': 'self',
        }
