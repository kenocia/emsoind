# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class AccountLoan(models.Model):
    _inherit = 'account.loan'

    kc_use_annuity_params = fields.Boolean(
        string='Parámetros del asistente guardados',
        default=False,
        copy=False,
        help='Se marca al confirmar "Calcular préstamo"; permite usar Recalcular con la misma tasa y método.',
    )
    kc_interest_rate = fields.Float(
        string='Tasa anual (asistente)',
        digits=(16, 6),
        copy=False,
        help='Copiada del asistente al guardar el cronograma.',
    )
    kc_payment_end_of_month = fields.Selection(
        selection=[
            ('end_of_month', 'End of Month'),
            ('at_anniversary', 'At Anniversary'),
        ],
        string='Tipo de pago (asistente)',
        copy=False,
    )
    kc_compounding_method = fields.Selection(
        selection=[
            ('30A/360', '30A/360'),
            ('30U/360', '30U/360'),
            ('30E/360', '30E/360'),
            ('30E/360 ISDA', '30E/360 ISDA'),
            ('A/360', 'A/360'),
            ('A/365F', 'A/365F'),
            ('A/A ISDA', 'A/A ISDA'),
            ('A/A AFB', 'A/A AFB'),
        ],
        string='Método de capitalización (asistente)',
        copy=False,
    )
    kc_first_payment_date = fields.Date(
        string='Primera cuota (asistente)',
        copy=False,
    )

    def _kc_nominal_monthly_rate(self):
        """Tasa mensual nominal a partir de la tasa anual del asistente (anual / 12)."""
        return (self.kc_interest_rate or 0.0) / 100.0 / 12.0

    def _action_recalculate_full_wizard(self):
        """Cronograma completo desde cero (mismo criterio que el asistente / pyloan)."""
        self.ensure_one()
        if self.duration % 12 != 0:
            raise UserError(_(
                'Para regenerar todo el cronograma desde cero, la duración debe ser múltiplo de 12 meses. '
                'Si solo ajustó la primera cuota, use «Recalcular» con al menos dos líneas: se conservará la primera.'
            ))
        loan_term_years = self.duration // 12
        if loan_term_years < 1:
            raise UserError(_('El plazo en años debe ser al menos 1.'))

        first_payment = self.kc_first_payment_date
        if not first_payment:
            first_payment = self.date.replace(day=1) + relativedelta(months=1)

        self.line_ids.unlink()
        wizard = self.env['account.loan.compute.wizard'].create({
            'loan_id': self.id,
            'loan_amount': self.amount_borrowed,
            'interest_rate': self.kc_interest_rate,
            'loan_term': loan_term_years,
            'start_date': self.date,
            'first_payment_date': first_payment,
            'payment_end_of_month': self.kc_payment_end_of_month or 'end_of_month',
            'compounding_method': self.kc_compounding_method or '30E/360',
        })
        return wizard.action_save()

    def _action_recalculate_preserve_first_line(self):
        """Mantiene la primera línea (cuota editada) y recalcula el resto como cuota nivelada."""
        self.ensure_one()
        currency = self.currency_id
        lines = self.line_ids.sorted(key=lambda l: (l.date, l.id))
        if len(lines) < 2:
            return self._action_recalculate_full_wizard()

        first = lines[0]
        tail = lines[1:]
        m = len(tail)
        if m < 1:
            return self._action_recalculate_full_wizard()

        if float_compare(first.principal, 0.0, precision_rounding=currency.rounding) <= 0:
            raise UserError(_('El principal de la primera cuota debe ser mayor que cero.'))

        balance_after_first = currency.round(self.amount_borrowed - first.principal)
        if float_compare(balance_after_first, 0.0, precision_rounding=currency.rounding) <= 0:
            raise UserError(_(
                'El principal de la primera cuota debe ser menor que el importe prestado para poder repartir el saldo en las cuotas restantes.'
            ))

        i = self._kc_nominal_monthly_rate()
        if float_compare(i, 0.0, precision_rounding=1e-12) == 0:
            level = currency.round(balance_after_first / m)
        else:
            r = float(i)
            b = float(balance_after_first)
            level_f = b * (r * (1.0 + r) ** m) / ((1.0 + r) ** m - 1.0)
            level = currency.round(level_f)

        tail.unlink()

        running = balance_after_first
        vals_list = []
        for j in range(m):
            pay_date = first.date + relativedelta(months=j + 1)
            last = j == m - 1
            if not last:
                int_amt = currency.round(running * i)
                prin = currency.round(level - int_amt)
                if float_compare(prin, running, precision_rounding=currency.rounding) > 0:
                    prin = running
                    int_amt = currency.round(level - prin)
            else:
                prin = running
                int_amt = currency.round(running * i)

            running = currency.round(running - prin)
            vals_list.append({
                'loan_id': self.id,
                'date': pay_date,
                'principal': prin,
                'interest': int_amt,
            })

        self.env['account.loan.line'].create(vals_list)

        # Ajuste de centavos: la suma de principales debe cuadrar con el importe prestado
        all_lines = self.line_ids.sorted(key=lambda l: (l.date, l.id))
        sum_prin = currency.round(sum(all_lines.mapped('principal')))
        diff = currency.round(self.amount_borrowed - sum_prin)
        if diff and len(all_lines) >= 2:
            last_line = all_lines[-1]
            last_line.principal = currency.round(last_line.principal + diff)

        total_interest = currency.round(sum(self.line_ids.mapped('interest')))
        self.write({'interest': total_interest})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Amortización'),
                'message': _(
                    'Se conservó la primera cuota y se recalcularon las demás sobre el saldo (tasa anual %(rate)s %% , reparto mensual nominal).',
                    rate=self.kc_interest_rate,
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_recalculate_schedule(self):
        """En borrador: si hay 2+ líneas, conserva la primera y recalcula el resto; si no, regenera todo con el asistente."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Solo se puede recalcular un préstamo en estado borrador.'))
        if not self.kc_use_annuity_params:
            raise UserError(_(
                'Primero abra «Calcular préstamo», defina la tasa y confirme para guardar el cronograma. '
                'Así se guardan la tasa y el método; después podrá ajustar la primera cuota y usar Recalcular.'
            ))
        if not self.name:
            raise UserError(_('Indique un nombre antes de recalcular.'))
        if not self.date:
            raise UserError(_('Indique la fecha del préstamo.'))
        if not self.duration or self.duration < 1:
            raise UserError(_('La duración debe ser al menos 1 mes.'))
        if float_compare(self.amount_borrowed, 0.0, precision_rounding=self.currency_id.rounding) <= 0:
            raise UserError(_('El importe prestado debe ser mayor que cero.'))

        if len(self.line_ids) >= 2:
            if len(self.line_ids) != self.duration:
                raise UserError(_(
                    'El número de líneas del cronograma (%(n)s) debe coincidir con la duración en meses (%(d)s).',
                    n=len(self.line_ids),
                    d=self.duration,
                ))
            return self._action_recalculate_preserve_first_line()

        return self._action_recalculate_full_wizard()
