# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, models
from odoo.exceptions import ValidationError


class AccountLoanComputeWizard(models.TransientModel):
    _inherit = 'account.loan.compute.wizard'

    def _validate_preview_inputs(self):
        """Mismas reglas que el onchange del estándar (sin depender del bus OWL)."""
        for wizard in self:
            if wizard.loan_amount < 0:
                raise ValidationError(_('El importe del préstamo debe ser positivo.'))
            if wizard.interest_rate < 0 or wizard.interest_rate > 100:
                raise ValidationError(_('La tasa de interés debe estar entre 0 y 100.'))
            if wizard.loan_term < 0:
                raise ValidationError(_('El plazo debe ser positivo.'))
            if (
                wizard.first_payment_date
                and wizard.start_date
                and wizard.start_date + relativedelta(years=wizard.loan_term) < wizard.first_payment_date
            ):
                raise ValidationError(_('La fecha del primer pago debe ser anterior al fin del préstamo.'))

    def action_refresh_preview(self):
        """Actualiza la previsualización con los valores actuales del formulario (tras guardar en servidor)."""
        self.ensure_one()
        self._validate_preview_inputs()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Previsualizar'),
                'message': _('Tabla de amortización actualizada.'),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_save(self):
        res = super().action_save()
        self.loan_id.write({
            'kc_use_annuity_params': True,
            'kc_interest_rate': self.interest_rate,
            'kc_payment_end_of_month': self.payment_end_of_month,
            'kc_compounding_method': self.compounding_method,
            'kc_first_payment_date': self.first_payment_date,
        })
        return res
