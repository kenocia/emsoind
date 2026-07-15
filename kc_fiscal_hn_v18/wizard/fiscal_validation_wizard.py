# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class FiscalValidationWizard(models.TransientModel):
    _name = 'kc_fiscal_hn.wizard.fiscal_validation'
    _description = 'Wizard de Validación Fiscal Masiva'

    # Campos para configuración
    date_from = fields.Date(string='Fecha Desde', required=True, default=fields.Date.today)
    date_to = fields.Date(string='Fecha Hasta', required=True, default=fields.Date.today)
    move_type = fields.Selection([
        ('out_invoice', 'Facturas de Cliente'),
        ('out_refund', 'Notas de Crédito'),
        ('in_invoice', 'Facturas de Proveedor'),
        ('in_refund', 'Notas de Débito')
    ], string='Tipo de Movimiento', default='out_invoice', required=True)
    
    # Campos para resultados
    total_invoices = fields.Integer(string='Total Facturas', readonly=True)
    validated_invoices = fields.Integer(string='Facturas Validadas', readonly=True)
    error_invoices = fields.Integer(string='Facturas con Errores', readonly=True)
    validation_details = fields.Text(string='Detalles de Validación', readonly=True)
    
    def action_validate_invoices(self):
        """Validar facturas en el rango de fechas especificado"""
        self.ensure_one()
        
        # Buscar facturas en el rango
        domain = [
            ('move_type', '=', self.move_type),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('state', 'in', ['draft', 'posted'])
        ]
        
        invoices = self.env['account.move'].search(domain)
        self.total_invoices = len(invoices)
        
        validated_count = 0
        error_count = 0
        error_details = []
        
        for invoice in invoices:
            try:
                # Validar montos fiscales
                invoice._validate_fiscal_amounts()
                
                # Validar campos obligatorios
                if invoice.move_type in ['out_invoice', 'out_refund']:
                    if not invoice.commercial_partner_id.vat and invoice.commercial_partner_id.country_id.code == 'HN':
                        raise ValidationError(f'Cliente sin RTN: {invoice.commercial_partner_id.name}')
                    
                    if invoice.requires_fiscal_numbering and not invoice.cai:
                        raise ValidationError(f'Factura requiere CAI: {invoice.name}')
                
                # Marcar como validada
                invoice.fiscal_validation_status = 'validated'
                invoice.fiscal_validation_message = _('Validada por proceso masivo')
                validated_count += 1
                
            except ValidationError as e:
                invoice.fiscal_validation_status = 'error'
                invoice.fiscal_validation_message = str(e)
                error_count += 1
                error_details.append(f"• {invoice.name}: {str(e)}")
        
        # Actualizar campos del wizard
        self.validated_invoices = validated_count
        self.error_invoices = error_count
        self.validation_details = self._format_validation_details(error_details)
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'kc_fiscal_hn.wizard.fiscal_validation',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    def _format_validation_details(self, error_details):
        """Formatear detalles de errores de validación"""
        if not error_details:
            return "Todas las facturas fueron validadas correctamente."
        
        result = "Errores encontrados:\n\n"
        for detail in error_details:
            result += f"{detail}\n"
        
        return result
    
    def action_fix_common_errors(self):
        """Intentar corregir errores comunes"""
        self.ensure_one()
        
        # Buscar facturas con errores
        domain = [
            ('move_type', '=', self.move_type),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('fiscal_validation_status', '=', 'error')
        ]
        
        error_invoices = self.env['account.move'].search(domain)
        fixed_count = 0
        
        for invoice in error_invoices:
            try:
                # Intentar recalcular montos
                invoice._compute_importe_gravado()
                invoice._compute_base_imponible()
                invoice._compute_isv_total()
                
                # Revalidar
                invoice._validate_fiscal_amounts()
                
                invoice.fiscal_validation_status = 'validated'
                invoice.fiscal_validation_message = _('Corregida automáticamente')
                fixed_count += 1
                
            except ValidationError:
                # Si no se puede corregir, mantener el error
                pass
        
        # Mostrar resultado
        message = f"Se corrigieron {fixed_count} facturas automáticamente."
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Corrección Automática'),
                'message': message,
                'type': 'success' if fixed_count > 0 else 'warning',
            }
        }
    
    def action_generate_report(self):
        """Generar reporte de validación fiscal"""
        self.ensure_one()
        
        # Buscar facturas en el rango
        domain = [
            ('move_type', '=', self.move_type),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('state', 'in', ['draft', 'posted'])
        ]
        
        invoices = self.env['account.move'].search(domain)
        
        # Generar reporte
        report_data = {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'move_type': dict(self._fields['move_type'].selection)[self.move_type],
            'total_invoices': len(invoices),
            'validated_invoices': len(invoices.filtered(lambda x: x.fiscal_validation_status == 'validated')),
            'error_invoices': len(invoices.filtered(lambda x: x.fiscal_validation_status == 'error')),
            'pending_invoices': len(invoices.filtered(lambda x: x.fiscal_validation_status == 'pending')),
            'total_isv': sum(invoices.mapped('isv_total')),
            'total_base_imponible': sum(invoices.mapped('base_imponible_total')),
        }
        
        # Aquí se implementaría la generación del reporte
        # Por ahora solo mostramos un resumen
        
        message = f"Reporte de Validación Fiscal:\n"
        message += f"• Período: {self.date_from} - {self.date_to}\n"
        message += f"• Total facturas: {report_data['total_invoices']}\n"
        message += f"• Validadas: {report_data['validated_invoices']}\n"
        message += f"• Con errores: {report_data['error_invoices']}\n"
        message += f"• Pendientes: {report_data['pending_invoices']}\n"
        message += f"• ISV total: L. {report_data['total_isv']:,.2f}\n"
        message += f"• Base imponible: L. {report_data['total_base_imponible']:,.2f}"
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reporte de Validación'),
                'message': message,
                'type': 'info',
            }
        } 