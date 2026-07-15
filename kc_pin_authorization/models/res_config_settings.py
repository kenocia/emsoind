# -*- coding: utf-8 -*-

from odoo import models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    def action_open_pin_rules(self):
        return self.env['ir.actions.act_window']._for_xml_id(
            'kc_pin_authorization.action_kc_pin_authorization_rule')

    def action_open_pin_logs(self):
        return self.env['ir.actions.act_window']._for_xml_id(
            'kc_pin_authorization.action_kc_pin_authorization_log')
