import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    fiscal_sequence_id = fields.Many2one(
        'ir.sequence',
        string='Secuencia Fiscal SAR',
        copy=False,
        check_company=True,
        domain="[('is_fiscal', '=', True), ('company_id', '=', company_id)]",
        help='Secuencia fiscal SAR para correlativos de facturas.',
    )
    refund_fiscal_sequence_id = fields.Many2one(
        'ir.sequence',
        string='Secuencia Fiscal Notas de Crédito',
        copy=False,
        check_company=True,
        domain="[('is_fiscal', '=', True), ('company_id', '=', company_id)]",
        help='Secuencia fiscal SAR para notas de crédito.',
    )
    document_fiscal = fields.Selection(
        string='Documento Fiscal',
        selection=[
            ('client', 'Factura Cliente'),
            ('vendors', 'Factura Proveedor (FA)'),
            ('boleta', 'Boleta de Compra'),
            ('extranjera', 'Compras Extranjera (FE)'),
            ('importacion', 'Importación (DUA/FYDUCA)'),
            ('retention', 'Comprobante de Retención'),
            ('credit', 'Nota de Crédito'),
            ('debit', 'Nota de Débito'),
        ],
    )
    fiscal_cai_active = fields.Char(
        string='CAI vigente',
        related='fiscal_sequence_id.active_cai_name',
        readonly=True,
    )
    fiscal_cai_uso = fields.Char(
        string='Consumo CAI',
        related='fiscal_sequence_id.active_cai_uso_label',
        readonly=True,
    )
    fiscal_cai_vence = fields.Date(
        string='Vence CAI',
        related='fiscal_sequence_id.active_cai_vence',
        readonly=True,
    )
    fiscal_cai_estado = fields.Selection(
        string='Estado CAI',
        related='fiscal_sequence_id.fiscal_list_estado',
        readonly=True,
    )
    fiscal_sequence_name = fields.Char(
        string='Secuencia SAR',
        related='fiscal_sequence_id.name',
        readonly=True,
    )
    fiscal_config_state = fields.Selection(
        selection=[
            ('ok', 'Configurado'),
            ('no_doc', 'Sin documento fiscal'),
            ('no_seq', 'Sin secuencia SAR'),
            ('seq_alert', 'CAI en alerta'),
            ('seq_critical', 'CAI crítico o vencido'),
        ],
        string='Estado configuración fiscal',
        compute='_compute_fiscal_config_state',
        store=True,
    )
    fiscal_is_operational = fields.Boolean(
        string='Operativo SAR',
        compute='_compute_fiscal_config_state',
        store=True,
    )

    @api.depends(
        'type',
        'document_fiscal',
        'fiscal_sequence_id',
        'fiscal_sequence_id.fiscal_list_estado',
        'fiscal_sequence_id.fiscal_list_vencida',
        'fiscal_sequence_id.fiscal_list_alerta',
    )
    def _compute_fiscal_config_state(self):
        for journal in self:
            journal.fiscal_is_operational = False
            if journal.type not in ('sale', 'purchase'):
                if journal.document_fiscal and not journal.fiscal_sequence_id:
                    journal.fiscal_config_state = 'no_seq'
                elif journal.document_fiscal:
                    journal.fiscal_config_state = 'ok'
                else:
                    journal.fiscal_config_state = 'no_doc'
                continue

            if not journal.document_fiscal:
                journal.fiscal_config_state = 'no_doc'
                continue
            if not journal.fiscal_sequence_id:
                journal.fiscal_config_state = 'no_seq'
                continue

            estado = journal.fiscal_sequence_id.fiscal_list_estado
            if journal.fiscal_sequence_id.fiscal_list_vencida:
                journal.fiscal_config_state = 'seq_critical'
            elif journal.fiscal_sequence_id.fiscal_list_alerta:
                journal.fiscal_config_state = 'seq_alert'
            elif estado in ('expired_date', 'expired_qty', 'sin_rango'):
                journal.fiscal_config_state = 'seq_critical'
            elif estado == 'warning':
                journal.fiscal_config_state = 'seq_alert'
            else:
                journal.fiscal_config_state = 'ok'
                journal.fiscal_is_operational = True

    def action_open_fiscal_sequence(self):
        self.ensure_one()
        if not self.fiscal_sequence_id:
            raise ValidationError(_(
                'El diario «%(journal)s» no tiene secuencia fiscal asignada.',
                journal=self.display_name,
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Secuencia Fiscal'),
            'res_model': 'ir.sequence',
            'res_id': self.fiscal_sequence_id.id,
            'view_mode': 'form',
            'view_id': self.env.ref(
                'kc_fiscal_hn_v18.ir_sequence_fiscal_form',
            ).id,
            'target': 'current',
        }

    @api.model
    def action_open_fiscal_journals_incomplete(self):
        """Abre diarios de venta/compra con configuración fiscal incompleta."""
        action = self.env['ir.actions.act_window']._for_xml_id(
            'kc_fiscal_hn_v18.action_fiscal_journals',
        )
        action['domain'] = [
            ('type', 'in', ['sale', 'purchase']),
            ('fiscal_config_state', '!=', 'ok'),
        ]
        action['context'] = dict(
            self.env.context,
            search_default_filter_incomplete=1,
        )
        return action

    @api.constrains('refund_fiscal_sequence_id', 'fiscal_sequence_id', 'document_fiscal')
    def _check_journal_fiscal_sequence(self):
        for journal in self:
            if not journal.document_fiscal:
                continue
            if (
                journal.refund_fiscal_sequence_id
                and journal.fiscal_sequence_id
                and journal.refund_fiscal_sequence_id == journal.fiscal_sequence_id
            ):
                raise ValidationError(_(
                    "En el diario '%s' no puede usar la misma secuencia fiscal "
                    "para facturas y notas de crédito.",
                    journal.display_name,
                ))
            for seq, label in (
                (journal.fiscal_sequence_id, _('Secuencia Fiscal SAR')),
                (journal.refund_fiscal_sequence_id, _('Secuencia Fiscal NC')),
            ):
                if seq and not seq.company_id:
                    raise ValidationError(_(
                        "La compañía no está definida en %(label)s '%(sequence)s' "
                        "del diario '%(journal)s'.",
                        label=label,
                        sequence=seq.display_name,
                        journal=journal.display_name,
                    ))

    def needs_fiscal_sequence(self, move_type=None):
        """True si el diario debe usar numeración fiscal SAR."""
        self.ensure_one()
        if not self.document_fiscal:
            return False
        if move_type:
            return move_type in ('out_invoice', 'in_invoice', 'out_refund', 'in_refund')
        return True

    def get_fiscal_sequence(self, move_type=None):
        """Devuelve la secuencia fiscal SAR según el tipo de movimiento."""
        self.ensure_one()
        if not self.needs_fiscal_sequence(move_type):
            return self.env['ir.sequence']
        if move_type in ('out_refund', 'in_refund') and self.refund_fiscal_sequence_id:
            return self.refund_fiscal_sequence_id
        return self.fiscal_sequence_id or self.env['ir.sequence']
