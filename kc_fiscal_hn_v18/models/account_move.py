# Copyright 2021 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, Command, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.safe_eval import safe_eval
import logging
import re

from .number_utilities import NumberUtilities

_logger = logging.getLogger(__name__)
_num_util = NumberUtilities()

# move_type + document_fiscal del diario → xmlid del reporte SAR (botón Imprimir)
_FISCAL_SAR_PDF_REPORTS = {
    ('out_invoice', 'client'): 'kc_fiscal_hn_v18.report_invoice_sar',
    ('out_refund', 'credit'): 'kc_fiscal_hn_v18.report_credit_note',
    ('out_invoice', 'debit'): 'kc_fiscal_hn_v18.report_debit_note',
    ('in_invoice', 'boleta'): 'kc_fiscal_hn_v18.report_boleta_compra',
    ('in_invoice', 'retention'): 'kc_fiscal_hn_v18.report_comprobante',
}

# Caracteres que rompen la regex de `sequence.mixin._compute_split_sequence`
# de Odoo (el comodín `.` no coincide con saltos de línea), provocando el error
# "'NoneType' object has no attribute 'start'" al confirmar la factura.
_FISCAL_NAME_INVALID_CHARS_RE = re.compile(
    r'[\r\n\t\v\f\x00-\x1f\x85\u2028\u2029]'
)

class AccountMove(models.Model):
    _inherit = "account.move"

    # Campo de motivo de emisión para notas de crédito
    motivo_emision = fields.Selection([
        ('anulacion', 'Anulación'),
        ('devolucion', 'Devolución'),
        ('descuento', 'Descuento')
    ], string='Motivo de Emisión',
       help='Motivo por el cual se emite la nota de crédito')

    # Campos fiscales de Honduras
    cai_proveedor = fields.Char(string='CAI Proveedor')
    correlativo_proveedor = fields.Char(
        string='N° Correlativo Proveedor', 
        help='Número de documento del proveedor (se usará como referencia)'
    )
    femision_proveedor = fields.Char(string='Fecha Emisión')
    cai = fields.Char(string='CAI', help='Clave de Autorización de Impresión', copy=False)
    fechaLimiteEmision = fields.Date(
        string='Fecha límite de emisión',
        help='Fecha límite del rango CAI vigente al publicar la factura '
             '(campo Hasta del correlativo SAR).',
        copy=False,
    )
    numeroInicial = fields.Char(
        string='Número inicial',
        help='Número inicial de facturación',
        copy=False,
    )
    numeroFinal = fields.Char(
        string='Número final',
        help='Número final de facturación',
        copy=False,
    )
    totalAmountString = fields.Char(string='Monto Total', help='Monto Total', copy=False)
    noOrdenCompraExenta = fields.Char(string='No OC exenta', help='Número de orden de compra exenta')
    noConsRegistroExonerado = fields.Char(string='No cons. reg. Exonerado', help='Número constancia de registro exonerado')
    noIdentificacionRegistroSAG = fields.Char(string='No ident. reg. SAG', help='Número identificación registro SAG')
    sale_order_id = fields.Many2one('sale.order', string='Pedido de Venta', compute='_get_saleorder', store=True)
    exonerado = fields.Boolean(string='Es exonerado', required=False, default=False)
    exento = fields.Boolean(string='Es exento', required=False, default=False)
    amount_discount = fields.Monetary(string='Descuento', store=True, compute='_compute_discount', readonly=True, currency_field='currency_id')
    amount_exento = fields.Monetary(string='Monto exento', store=True, compute='_compute_exent', readonly=True, currency_field='currency_id')
    amount_exonerado = fields.Monetary(string='Monto exonerado', store=True, compute='_compute_exent', readonly=True, currency_field='currency_id')
    amount_isv15 = fields.Monetary(string='Isv 15%', store=True, compute='_compute_importe_gravado', readonly=True, currency_field='currency_id')
    gravado_isv15 = fields.Monetary(string='Importe Gravado 15%', store=True, compute='_compute_importe_gravado', readonly=True, currency_field='currency_id')
    amount_isv18 = fields.Monetary(string='Isv 18%', store=True, compute='_compute_importe_gravado', readonly=True, currency_field='currency_id')
    gravado_isv18 = fields.Monetary(string='Importe Gravado 18%', store=True, compute='_compute_importe_gravado', readonly=True, currency_field='currency_id')
    depto = fields.Many2one("res.country.state", string='Departamento', related='partner_id.state_id', store=True)
    class_document_sar = fields.Selection(string='Clase de Documento SAR', selection=[('FA', 'FA-FACTURA'), ('OC', 'OC-OTROS COMPROBANTES DE PAGO')], required=False, )
    montos_sar = fields.Selection(string='Montos SAR', selection=[('costo', 'Monto al Costo'), ('gasto', 'Monto al Gasto'), ('no_deducible', 'Valor no deducible')], default='gasto', required=False, )

    # Clasificación DMC automática
    seccion_dmc = fields.Selection([
        ('A', 'Sección A — Compras Locales'),
        ('B', 'Sección B — Comprobantes Eventuales'),
        ('C', 'Sección C — Importaciones'),
        ('NA', 'No aplica DMC'),
    ], string='Sección DMC',
       compute='_compute_seccion_dmc',
       store=True,
       help='Sección del formulario DMC donde se '
            'reporta esta compra. Se determina '
            'automáticamente según el tipo de diario.',
    )
    numero_dua = fields.Char(
        string='N° DUA',
        help='Número de Declaración Única Aduanera '
             'para importaciones.',
    )
    tipo_compra_dmc = fields.Selection([
        ('fa_gravada_15', 'FA Gravada 15%'),
        ('fa_gravada_18', 'FA Gravada 18%'),
        ('fa_exenta', 'FA Exenta'),
        ('fa_exonerada', 'FA Exonerada (OCE)'),
        ('oc_gravada', 'OC Gravada'),
        ('oc_exenta', 'OC Exenta'),
        ('boleta', 'Boleta de Compra'),
        ('importacion_15', 'Importación Gravada 15%'),
        ('importacion_18', 'Importación Gravada 18%'),
        ('importacion_exenta', 'Importación Exenta'),
        ('fyduca', 'FYDUCA (Guatemala)'),
        ('na', 'No aplica'),
    ], string='Tipo Compra DMC',
       compute='_compute_tipo_compra_dmc',
       store=True,
       help='Clasificación específica para el '
            'formulario DMC del SAR Honduras.',
    )
    obligado_dmc = fields.Boolean(
        related='company_id.obligado_dmc',
        readonly=True,
    )

    info_fiscal_proveedor = fields.Char(
        string='Info Fiscal Proveedor',
        compute='_compute_info_fiscal_proveedor',
        help='Información fiscal del proveedor para esta factura.',
    )
    alerta_fiscal_factura = fields.Selection([
        ('ok', 'OK'),
        ('warning', 'Advertencia'),
        ('error', 'Error'),
        ('info', 'Información'),
    ], compute='_compute_info_fiscal_proveedor',
    )

    document_fiscal = fields.Selection(
        string='Documento Fiscal',
        related='journal_id.document_fiscal',
        store=True,
        readonly=True,
    )
    diario_fiscal_bloqueado = fields.Boolean(
        string='Diario Fiscal Bloqueado',
        compute='_compute_diario_fiscal_bloqueado',
        help='Verdadero cuando el proveedor tiene un diario de compra '
             'asignado por su clasificación fiscal; en ese caso el diario '
             'no puede cambiarse manualmente.',
    )
    invoice_retention = fields.Many2one("account.move", string="Factura de retención", domain="[('move_type', '=', 'in_invoice'), ('partner_id', '=', partner_id)]")
    original_print = fields.Boolean(string='Original', default=True)
    vendedor_empleado = fields.Many2one("hr.employee", string='Vendedor Empleado')

    # Campos adicionales para control fiscal mejorado
    fiscal_validation_status = fields.Selection([
        ('pending', 'Pendiente'),
        ('validated', 'Validado'),
        ('error', 'Error')
    ], string='Estado Validación Fiscal', default='pending', readonly=True)
    fiscal_validation_message = fields.Text(string='Mensaje Validación Fiscal', readonly=True)
    requires_fiscal_numbering = fields.Boolean(string='Requiere Numeración Fiscal', compute='_compute_requires_fiscal_numbering', store=True)
    base_imponible_total = fields.Monetary(string='Base Imponible Total', compute='_compute_base_imponible', store=True, readonly=True, currency_field='currency_id')
    isv_total = fields.Monetary(string='ISV Total', compute='_compute_isv_total', store=True, readonly=True, currency_field='currency_id')

    # ── Control de Libros SAR ─────────────────────────
    in_libro_ventas = fields.Boolean(
        string='En Libro Ventas SAR',
        default=False,
        readonly=True,
        copy=False,
        tracking=True,
    )
    libro_ventas_id = fields.Many2one(
        'kc_fiscal_hn.book.sales',
        string='Libro Ventas SAR',
        readonly=True,
        copy=False,
        ondelete='set null',
    )
    libro_ventas_estado = fields.Selection(
        related='libro_ventas_id.state',
        string='Estado Libro Ventas',
        readonly=True,
        store=True,
    )
    in_libro_compras = fields.Boolean(
        string='En Libro Compras SAR',
        default=False,
        readonly=True,
        copy=False,
        tracking=True,
    )
    libro_compras_id = fields.Many2one(
        'kc_fiscal_hn.book.purchases',
        string='Libro Compras SAR',
        readonly=True,
        copy=False,
        ondelete='set null',
    )
    libro_compras_estado = fields.Selection(
        related='libro_compras_id.state',
        string='Estado Libro Compras',
        readonly=True,
        store=True,
    )
    in_libro_retenciones = fields.Boolean(
        string='En Libro Retenciones SAR',
        default=False,
        readonly=True,
        copy=False,
        tracking=True,
    )
    libro_retenciones_id = fields.Many2one(
        'kc_fiscal_hn.book.retentions',
        string='Libro Retenciones SAR',
        readonly=True,
        copy=False,
        ondelete='set null',
    )
    estado_sar = fields.Selection([
        ('no_incluida', 'Sin declarar'),
        ('en_libro', 'En libro SAR'),
        ('declarada', 'Declarada al SAR'),
        ('rectificada', 'Rectificada'),
    ], string='Estado SAR',
       compute='_compute_estado_sar',
       store=True,
       tracking=True,
    )
    tipo_documento_sar = fields.Selection([
        ('factura', 'Factura'),
        ('nota_credito', 'Nota de Crédito'),
        ('nota_debito', 'Nota de Débito'),
        ('retencion', 'Comprobante Retención'),
    ], string='Tipo Documento SAR',
       compute='_compute_tipo_documento_sar',
       store=True,
    )
    
    # Campo computado para mostrar la referencia completa
    referencia_completa = fields.Char(
        string='Referencia Completa',
        compute='_compute_referencia_completa',
        store=True,
        help='Referencia completa que incluye el número del documento y el correlativo del proveedor'
    )
    
    # Campo para controlar importación de documentos históricos
    is_import = fields.Boolean(
        string='Es Importado',
        default=False,
        help='Marcar como True para documentos importados, no requieren correlativo fiscal'
    )
    # Si False, no se debe mostrar el botón Confirmar (fecha o rango fiscal vencido sin subsecuencias)
    fiscal_can_confirm = fields.Boolean(
        string='Puede confirmar (fiscal)',
        compute='_compute_fiscal_can_confirm',
        help='False cuando la fecha o el rango de numeración fiscal ha vencido y no hay subsecuencias futuras'
    )
    fiscal_can_manage_cancel = fields.Boolean(
        string='Admin numeración fiscal',
        compute='_compute_fiscal_can_manage_cancel',
        help='True si el usuario pertenece al grupo Administrador de Numeración Fiscal',
    )
    amount_words = fields.Char(
        string='Monto en Letras',
        compute='_compute_amount_words',
        help='Monto total en letras para reportes SAR',
    )

    # def action_print_document(self):
    #     """
    #     Método personalizado para imprimir documentos y marcar original_print como True
    #     """
    #     self.ensure_one()
        
    #     # Marcar el documento como impreso
    #     self.write({'original_print': True})
        
    #     # Registrar la acción de impresión
    #     _logger.info(f"Documento {self.name} marcado como impreso")
        
    #     # Retornar la acción de impresión del reporte correspondiente
    #     if self.move_type == 'out_invoice':
    #         return self.env.ref('kc_fiscal_hn.report_invoice_sar').report_action(self)
    #     elif self.move_type == 'out_refund':
    #         return self.env.ref('kc_fiscal_hn.report_credit_note').report_action(self)
    #     elif self.move_type == 'in_invoice':
    #         return self.env.ref('kc_fiscal_hn.report_boleta_compra').report_action(self)
    #     else:
    #         # Para otros tipos de documentos, usar el reporte por defecto
    #         return self.env.ref('account.action_report_invoice').report_action(self)

    # def action_print_original(self):
    #     """
    #     Método específico para imprimir original
    #     """
    #     self.ensure_one()
        
    #     # Marcar el documento como impreso
    #     self.write({'original_print': True})
        
    #     # Registrar la acción de impresión
    #     _logger.info(f"Documento {self.name} marcado como impreso (original)")
        
    #     # Retornar la acción de impresión del reporte correspondiente
    #     if self.move_type == 'out_invoice':
    #         return self.env.ref('kc_fiscal_hn.report_invoice_sar').report_action(self)
    #     elif self.move_type == 'out_refund':
    #         return self.env.ref('kc_fiscal_hn.report_credit_note').report_action(self)
    #     elif self.move_type == 'in_invoice':
    #         return self.env.ref('kc_fiscal_hn.report_boleta_compra').report_action(self)
    #     else:
    #         # Para otros tipos de documentos, usar el reporte por defecto
    #         return self.env.ref('account.action_report_invoice').report_action(self)


    # We must by-pass this constraint of sequence.mixin
    def _constrains_date_sequence(self):
        return True

    def copy(self, default=None):
        """Al duplicar, limpiar numeración SAR para asignar correlativo nuevo al confirmar."""
        default = dict(default or {})
        default.update({
            'name': '/',
            'cai': False,
            'numeroInicial': False,
            'numeroFinal': False,
            'fechaLimiteEmision': False,
            'totalAmountString': False,
            'fiscal_validation_status': 'pending',
            'fiscal_validation_message': False,
            'original_print': True,
        })
        return super().copy(default)

    @api.depends('move_type', 'journal_id.document_fiscal')
    def _compute_tipo_documento_sar(self):
        for move in self:
            if move.move_type in ('out_invoice', 'in_invoice'):
                if move.journal_id.document_fiscal == 'debit':
                    move.tipo_documento_sar = 'nota_debito'
                elif move.journal_id.document_fiscal == 'retention':
                    move.tipo_documento_sar = 'retencion'
                else:
                    move.tipo_documento_sar = 'factura'
            elif move.move_type in ('out_refund', 'in_refund'):
                move.tipo_documento_sar = 'nota_credito'
            else:
                move.tipo_documento_sar = False

    @api.depends(
        'partner_id',
        'partner_id.constancia_vigente',
        'partner_id.alerta_constancia',
        'partner_id.tipo_fiscal_proveedor',
        'move_type',
    )
    def _compute_info_fiscal_proveedor(self) -> None:
        for move in self:
            if move.move_type != 'in_invoice':
                move.info_fiscal_proveedor = ''
                move.alerta_fiscal_factura = 'ok'
                continue
            partner = move.partner_id
            if not partner:
                move.info_fiscal_proveedor = ''
                move.alerta_fiscal_factura = 'ok'
                continue
            tipo = partner.tipo_fiscal_proveedor
            if not tipo:
                move.info_fiscal_proveedor = (
                    '⚠️ Configure el país del proveedor'
                )
                move.alerta_fiscal_factura = 'warning'
                continue
            if tipo in ('extranjero_ca', 'extranjero'):
                move.info_fiscal_proveedor = (
                    'ℹ️ Proveedor extranjero — Diario Importaciones. '
                    'ISV se paga en aduana. Sin retención ISR/ISV.'
                )
                move.alerta_fiscal_factura = 'info'
            elif tipo == 'nacional_sin_rtn':
                move.info_fiscal_proveedor = (
                    'ℹ️ Sin RTN — Boleta de Compra. '
                    'Sin retención ISR. Sección DMC: B'
                )
                move.alerta_fiscal_factura = 'info'
            elif partner.alerta_constancia == 'vencida':
                move.info_fiscal_proveedor = (
                    f'🔴 Constancia vencida desde '
                    f'{partner.fecha_vencimiento_constancia}'
                    f' — Se aplicará retención ISR '
                    f'según tipo de compra.'
                )
                move.alerta_fiscal_factura = 'error'
            elif partner.alerta_constancia == 'proximo':
                move.info_fiscal_proveedor = (
                    f'⚠️ Constancia vence en '
                    f'{partner.dias_vencimiento_constancia} días '
                    f'({partner.fecha_vencimiento_constancia})'
                    f' — Solicite renovación.'
                )
                move.alerta_fiscal_factura = 'warning'
            elif partner.constancia_vigente:
                move.info_fiscal_proveedor = (
                    f'✅ Constancia vigente hasta '
                    f'{partner.fecha_vencimiento_constancia}'
                    f' — Sin retención ISR.'
                )
                move.alerta_fiscal_factura = 'ok'
            else:
                move.info_fiscal_proveedor = (
                    '⚠️ Sin constancia de pago a cuenta. '
                    'Se aplicará retención ISR según tipo de compra.'
                )
                move.alerta_fiscal_factura = 'warning'

    @api.onchange('partner_id')
    def _onchange_partner_diario_fiscal_hn(self):
        """Sugiere diario de compra según clasificación fiscal del proveedor."""
        if self.move_type != 'in_invoice' or not self.partner_id:
            return
        diario_sugerido = self.partner_id.diario_compra_sugerido_id
        if not diario_sugerido:
            return
        if not self.journal_id:
            self.journal_id = diario_sugerido
        elif self.journal_id.document_fiscal != diario_sugerido.document_fiscal:
            self.journal_id = diario_sugerido

    @api.depends(
        'move_type',
        'journal_id.document_fiscal',
        'journal_id.type',
        'class_document_sar',
        'commercial_partner_id.vat',
        'commercial_partner_id.country_id',
    )
    def _compute_seccion_dmc(self):
        """Determina la sección DMC según el tipo de diario."""
        for move in self:
            if move.move_type not in ('in_invoice', 'in_refund'):
                move.seccion_dmc = 'NA'
                continue

            doc_fiscal = move.journal_id.document_fiscal or ''

            if doc_fiscal in ('importacion', 'extranjera'):
                move.seccion_dmc = 'C'
            elif doc_fiscal == 'boleta':
                move.seccion_dmc = 'B'
            elif (
                move.class_document_sar == 'OC'
                and not move.commercial_partner_id.vat
            ):
                move.seccion_dmc = 'B'
            elif doc_fiscal in ('vendors', 'retention'):
                move.seccion_dmc = 'A'
            elif move.journal_id.type == 'purchase':
                # Diario de compras estándar sin clasificación explícita
                move.seccion_dmc = 'A'
            else:
                move.seccion_dmc = 'NA'

    @api.depends(
        'seccion_dmc',
        'class_document_sar',
        'amount_exento',
        'amount_exonerado',
        'gravado_isv15',
        'gravado_isv18',
        'partner_id.country_id',
    )
    def _compute_tipo_compra_dmc(self):
        """Clasifica el tipo específico de compra para la DMC."""
        for move in self:
            if move.seccion_dmc == 'NA':
                move.tipo_compra_dmc = 'na'
                continue

            seccion = move.seccion_dmc
            clase = move.class_document_sar or 'FA'

            if seccion == 'C':
                if (
                    move.partner_id.country_id
                    and move.partner_id.country_id.code == 'GT'
                ):
                    move.tipo_compra_dmc = 'fyduca'
                elif move.amount_exento > 0:
                    move.tipo_compra_dmc = 'importacion_exenta'
                elif move.gravado_isv18 > 0:
                    move.tipo_compra_dmc = 'importacion_18'
                else:
                    move.tipo_compra_dmc = 'importacion_15'

            elif seccion == 'B':
                move.tipo_compra_dmc = 'boleta'

            else:
                if move.amount_exonerado > 0:
                    move.tipo_compra_dmc = (
                        'fa_exonerada' if clase == 'FA' else 'oc_exenta'
                    )
                elif move.amount_exento > 0:
                    move.tipo_compra_dmc = (
                        'fa_exenta' if clase == 'FA' else 'oc_exenta'
                    )
                elif move.gravado_isv18 > 0:
                    move.tipo_compra_dmc = 'fa_gravada_18'
                elif clase == 'OC':
                    move.tipo_compra_dmc = 'oc_gravada'
                else:
                    move.tipo_compra_dmc = 'fa_gravada_15'

    def _validate_compra_dmc(self):
        """
        Valida datos requeridos para la DMC según tipo de diario.
        Solo aplica para contribuyentes obligados a DMC.
        """
        for move in self:
            if move.move_type != 'in_invoice':
                continue
            if not move.company_id.obligado_dmc:
                continue
            if move.seccion_dmc == 'NA':
                continue

            doc_fiscal = move.journal_id.document_fiscal or ''

            if (
                move.seccion_dmc == 'A'
                and doc_fiscal == 'vendors'
                and move.class_document_sar == 'FA'
                and not move.commercial_partner_id.vat
                and move.commercial_partner_id.country_id
                and move.commercial_partner_id.country_id.code == 'HN'
            ):
                _logger.warning(
                    'Factura %s sin RTN proveedor. '
                    'El SAR puede rechazar el crédito '
                    'fiscal de esta compra.',
                    move.name or move.id,
                )

            if (
                move.seccion_dmc == 'C'
                and not move.numero_dua
                and doc_fiscal in ('importacion', 'extranjera')
            ):
                raise UserError(_(
                    'Las compras extranjeras / importaciones requieren '
                    'el número de DUA (Declaración Única Aduanera) '
                    'para la DMC.\n\n'
                    'Ingrese el N° DUA en la '
                    'pestaña SAR de la factura.'
                ))

    @api.depends(
        'in_libro_ventas',
        'in_libro_compras',
        'in_libro_retenciones',
        'libro_ventas_estado',
        'libro_compras_estado',
    )
    def _compute_estado_sar(self):
        for move in self:
            en_libro = (
                move.in_libro_ventas
                or move.in_libro_compras
                or move.in_libro_retenciones
            )
            if not en_libro:
                move.estado_sar = 'no_incluida'
                continue
            estado = (
                move.libro_ventas_estado
                or move.libro_compras_estado
                or 'pending'
            )
            mapping = {
                'declared': 'declarada',
                'rectified': 'rectificada',
                'pending': 'en_libro',
                'draft': 'en_libro',
            }
            move.estado_sar = mapping.get(estado, 'en_libro')

    def _check_sar_declared_protection(self):
        """Bloquea modificación de documentos ya declarados al SAR."""
        for move in self:
            if move.estado_sar != 'declarada':
                continue
            libro_nombre = (
                move.libro_ventas_id.name
                or move.libro_compras_id.name
                or move.libro_retenciones_id.display_name
                or 'Libro SAR'
            )
            raise UserError(_(
                'El documento %(doc)s ya fue declarado al '
                'SAR en el libro "%(libro)s".\n\n'
                'Los documentos declarados no pueden '
                'modificarse ni cancelarse.\n\n'
                'Si necesita corregir:\n'
                '• Emita una Nota de Crédito vinculada\n'
                '• Contacte al contador responsable',
                doc=move.name,
                libro=libro_nombre,
            ))

    def _get_fiscal_sar_pdf_report(self):
        """Reporte PDF SAR según tipo de movimiento y documento fiscal del diario."""
        self.ensure_one()
        doc_fiscal = self.journal_id.document_fiscal
        if not doc_fiscal:
            return self.env['ir.actions.report']
        xmlid = _FISCAL_SAR_PDF_REPORTS.get((self.move_type, doc_fiscal))
        if not xmlid:
            return self.env['ir.actions.report']
        report = self.env.ref(xmlid, raise_if_not_found=False)
        return report or self.env['ir.actions.report']

    def _get_invoice_report_filename(self, extension='pdf'):
        """Nombre de archivo PDF: reporte SAR si el diario es fiscal."""
        self.ensure_one()
        sar_report = self._get_fiscal_sar_pdf_report()
        report_id = (
            self.env.context.get('invoice_report')
            or self.partner_id.invoice_template_pdf_report_id
            or sar_report
            or self.env.ref('account.account_invoices')
        )
        if not report_id.print_report_name:
            return False
        file_name = safe_eval(report_id.print_report_name, {'object': self})
        return f"{file_name.replace('/', '_')}.{extension}"

    def _is_fiscal_invoice(self):
        """
        Retorna True si la factura es una factura de cliente
        con secuencia fiscal SAR activa.
        Solo aplica a out_invoice, no a otros documentos.
        """
        self.ensure_one()
        return (
            self.move_type == 'out_invoice'
            and self.journal_id.document_fiscal == 'client'
            and bool(self.journal_id.fiscal_sequence_id)
        )

    def _check_fiscal_cancel_permission(self):
        """
        Verifica que el usuario tenga permiso para cancelar
        documentos fiscales SAR.
        Lanza AccessError si no tiene el grupo requerido.
        """
        self.ensure_one()
        if not self._is_fiscal_invoice():
            return
        if self.state != 'posted':
            return

        is_fiscal_admin = self.env.user.has_group(
            'kc_fiscal_hn_v18.group_fiscal_sequence_manager'
        )
        if not is_fiscal_admin:
            raise AccessError(_(
                'No puede cancelar esta factura fiscal.\n\n'
                'Las facturas con numeración SAR confirmadas '
                'deben anularse mediante una Nota de Crédito.\n\n'
                'Si necesita cancelar por error de sistema, '
                'contacte al Administrador de Numeración Fiscal.'
            ))

    def button_cancel(self):
        self._check_sar_declared_protection()
        for move in self:
            move._check_fiscal_cancel_permission()
        return super().button_cancel()

    def button_draft(self):
        self._check_sar_declared_protection()
        for move in self:
            if move._is_fiscal_invoice() and move.state == 'posted':
                is_fiscal_admin = self.env.user.has_group(
                    'kc_fiscal_hn_v18.group_fiscal_sequence_manager'
                )
                if not is_fiscal_admin:
                    raise AccessError(_(
                        'No puede resetear a borrador esta factura '
                        'fiscal SAR.\n\n'
                        'Use una Nota de Crédito para anularla.\n\n'
                        'Contacte al Administrador de Numeración '
                        'Fiscal si necesita acceso especial.'
                    ))
        return super().button_draft()

    def unlink(self):
        for move in self:
            if move._is_fiscal_invoice():
                if move.state == 'posted':
                    raise UserError(_(
                        'No puede eliminar la factura fiscal %s.\n\n'
                        'Las facturas fiscales confirmadas no pueden '
                        'eliminarse. Use una Nota de Crédito.'
                    ) % move.name)
                if move.state == 'cancel':
                    is_fiscal_admin = self.env.user.has_group(
                        'kc_fiscal_hn_v18.group_fiscal_sequence_manager'
                    )
                    if not is_fiscal_admin:
                        raise AccessError(_(
                            'No puede eliminar la factura fiscal '
                            'cancelada %s.\n\n'
                            'Solo el Administrador de Numeración '
                            'Fiscal puede eliminar facturas '
                            'fiscales canceladas.'
                        ) % move.name)
        return super().unlink()

    @api.depends('move_type', 'partner_id', 'partner_id.diario_compra_sugerido_id')
    def _compute_diario_fiscal_bloqueado(self):
        for move in self:
            move.diario_fiscal_bloqueado = bool(
                move.move_type == 'in_invoice'
                and move.partner_id.diario_compra_sugerido_id
            )

    @api.model
    def _forzar_diario_compra_fiscal_hn(self, vals):
        """Fuerza el diario de compra según la clasificación del proveedor.

        Garantiza el ruteo a Compras Nacionales (FA) / Compras Extranjera (FE)
        / Importaciones aun cuando el registro se cree por importación o API,
        de modo que el usuario no pueda asignar un diario distinto.
        """
        move_type = vals.get('move_type') or self.env.context.get('default_move_type')
        if move_type != 'in_invoice':
            return
        partner_id = vals.get('partner_id')
        if not partner_id:
            return
        diario = self.env['res.partner'].browse(partner_id).diario_compra_sugerido_id
        if diario:
            vals['journal_id'] = diario.id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._forzar_diario_compra_fiscal_hn(vals)
        return super().create(vals_list)

    def write(self, vals):
        campos_fiscales = {
            'invoice_line_ids', 'partner_id',
            'invoice_date', 'journal_id',
        }
        if campos_fiscales & set(vals.keys()):
            self._check_sar_declared_protection()
        # Si cambia el proveedor en una factura de compra, re-rutear el diario
        # a su diario fiscal y evitar que se altere manualmente.
        if vals.get('partner_id') and any(
            move.move_type == 'in_invoice' for move in self
        ):
            diario = self.env['res.partner'].browse(
                vals['partner_id']
            ).diario_compra_sugerido_id
            if diario:
                vals['journal_id'] = diario.id
        return super().write(vals)

    def _is_end_of_seq_chain(self):
        invoices_no_gap_sequences = self.filtered(
            lambda inv: (
                inv.journal_id.get_fiscal_sequence(inv.move_type)
                and inv.journal_id.get_fiscal_sequence(inv.move_type).implementation == 'no_gap'
            )
        )
        invoices_other_sequences = self - invoices_no_gap_sequences
        if not invoices_other_sequences and invoices_no_gap_sequences:
            return False
        return super(AccountMove, invoices_other_sequences)._is_end_of_seq_chain()

    def _fiscal_invoice_lines(self, move):
        """Líneas de producto con importe (Odoo 18: display_type='product'; excluye secciones/notas)."""
        return move.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product' or (not l.display_type and l.product_id)
        )

    @staticmethod
    def _fiscal_tax_group_lower(tax):
        return (tax.tax_group_id.name or '').strip().lower()

    def _find_sales_tax(self, base_domain):
        """Busca un impuesto de ventas priorizando los que tienen código SAR
        (impuestos HN del módulo) sobre los genéricos de Odoo."""
        self.ensure_one()
        Tax = self.env['account.tax']
        domain = [
            ('company_id', '=', self.company_id.id),
            ('type_tax_use', '=', 'sale'),
            ('active', '=', True),
        ] + base_domain
        tax = Tax.search(domain + [('codigo_sar_id', '!=', False)], limit=1)
        return tax or Tax.search(domain, limit=1)

    def _get_default_sales_isv_tax(self):
        """Impuesto ISV 15% de ventas de la compañía (para auto-aplicar)."""
        return self._find_sales_tax([
            ('tipo_impuesto', '=', 'isv'),
            ('amount', '=', 15.0),
        ])

    def _get_sales_exonerado_tax(self):
        """Impuesto Exonerado 0% de ventas de la compañía."""
        return self._find_sales_tax([('tipo_impuesto', '=', 'exonerado')])

    def _apply_fiscal_default_taxes(self):
        """Normaliza los impuestos de las líneas de venta antes de publicar.

        - Toda línea de producto sin impuesto recibe ISV 15% (gravado por
          defecto), para no subdeclarar ISV ante el SAR.
        - Si la factura es exonerada (``exonerado``), los impuestos ISV de las
          líneas se sustituyen por el impuesto Exonerado 0% (Opción 1).
        """
        for inv in self:
            if inv.move_type not in ('out_invoice', 'out_refund') or inv.is_import:
                continue

            isv_tax = inv._get_default_sales_isv_tax()
            if isv_tax:
                for line in inv._fiscal_invoice_lines(inv):
                    if not line.tax_ids:
                        line.tax_ids = [Command.set(isv_tax.ids)]
            else:
                _logger.warning(
                    'No se encontró impuesto ISV 15%% de ventas para la '
                    'compañía %s; no se pudo auto-aplicar a la factura %s.',
                    inv.company_id.display_name, inv.id,
                )

            if inv.exonerado:
                exon_tax = inv._get_sales_exonerado_tax()
                if exon_tax:
                    for line in inv._fiscal_invoice_lines(inv):
                        isv_lines = line.tax_ids.filtered(
                            lambda t: t.tipo_impuesto == 'isv'
                        )
                        if isv_lines:
                            restantes = line.tax_ids - isv_lines
                            line.tax_ids = [
                                Command.set((restantes + exon_tax).ids)
                            ]
                else:
                    _logger.warning(
                        'Factura %s marcada como exonerada pero no existe '
                        'impuesto Exonerado 0%% de ventas en la compañía %s.',
                        inv.id, inv.company_id.display_name,
                    )

    def _fiscal_line_is_exempt(self, line):
        """Línea exenta de ISV.

        Criterio principal: la línea tiene un impuesto con
        ``tipo_impuesto == 'exento'`` (fuente de verdad del módulo, igual que
        Libros SAR y Dashboard). Respaldos: nombre del grupo de impuesto
        (datos antiguos) y líneas sin impuesto.
        """
        if not line.tax_ids:
            return True
        if any(t.tipo_impuesto == 'exento' for t in line.tax_ids):
            return True
        return any('exento' in self._fiscal_tax_group_lower(t) for t in line.tax_ids)

    def _fiscal_line_is_exonerated(self, line):
        """Línea exonerada de ISV (por ``tipo_impuesto == 'exonerado'``)."""
        if not line.tax_ids:
            return False
        if any(t.tipo_impuesto == 'exonerado' for t in line.tax_ids):
            return True
        return any('exonerado' in self._fiscal_tax_group_lower(t) for t in line.tax_ids)

    @api.depends(
        'invoice_line_ids.discount',
        'invoice_line_ids.price_unit',
        'invoice_line_ids.quantity',
        'invoice_line_ids.price_subtotal',
        'invoice_line_ids.product_id',
        'invoice_line_ids.display_type',
        'move_type',
        'currency_id',
    )
    def _compute_discount(self):
        """Total descuentos otorgados (informativo). amount_untaxed / apuntes ya llevan el neto por línea."""
        for inv in self:
            if not inv.is_invoice(include_receipts=True):
                inv.amount_discount = 0.0
                continue
            discount_total = 0.0
            for line in self._fiscal_invoice_lines(inv):
                if line.discount:
                    gross = line.quantity * line.price_unit
                    discount_total += abs(gross * (line.discount / 100.0))
                elif line.product_id and line.product_id.product_tmpl_id.default_code == 'Desc':
                    discount_total += abs(line.price_subtotal)
            inv.amount_discount = inv.currency_id.round(discount_total) if inv.currency_id else round(discount_total, 4)

    @api.depends(
        'invoice_line_ids.tax_ids',
        'invoice_line_ids.price_subtotal',
        'invoice_line_ids.display_type',
        'move_type',
        'currency_id',
    )
    def _compute_exent(self):
        for inv in self:
            if not inv.is_invoice(include_receipts=True):
                inv.amount_exento = 0.0
                inv.amount_exonerado = 0.0
                continue
            exento = 0.0
            exonerado = 0.0
            for line in self._fiscal_invoice_lines(inv):
                net_untaxed = line.price_subtotal
                if self._fiscal_line_is_exempt(line):
                    exento += net_untaxed
                if self._fiscal_line_is_exonerated(line):
                    exonerado += net_untaxed
            inv.amount_exento = inv.currency_id.round(exento) if inv.currency_id else round(exento, 4)
            inv.amount_exonerado = inv.currency_id.round(exonerado) if inv.currency_id else round(exonerado, 4)

    @api.depends(
        'invoice_line_ids.tax_ids',
        'invoice_line_ids.price_subtotal',
        'invoice_line_ids.display_type',
        'move_type',
    )
    def _compute_importe_gravado(self):
        """ISV SAR: base por línea = price_subtotal (neto de descuento); mismo criterio que los apuntes contables."""
        for inv in self:
            if not inv.is_invoice(include_receipts=True):
                inv.amount_isv15 = 0.0
                inv.gravado_isv15 = 0.0
                inv.amount_isv18 = 0.0
                inv.gravado_isv18 = 0.0
                continue
            isv15 = 0.0
            isv18 = 0.0
            importe15 = 0.0
            importe18 = 0.0
            for line in self._fiscal_invoice_lines(inv):
                base_imponible = line.price_subtotal
                if self._fiscal_line_is_exempt(line) or self._fiscal_line_is_exonerated(line):
                    continue
                for tax in line.tax_ids:
                    # Solo impuestos ISV (excluye retenciones u otros con
                    # tasa 15/18 que no son ISV).
                    if tax.tipo_impuesto != 'isv':
                        continue
                    if tax.amount == 15:
                        isv15 += self._round_sar(base_imponible * 0.15)
                        importe15 += base_imponible
                    elif tax.amount == 18:
                        isv18 += self._round_sar(base_imponible * 0.18)
                        importe18 += base_imponible
            inv.amount_isv15 = self._round_sar(isv15)
            inv.gravado_isv15 = self._round_sar(importe15)
            inv.amount_isv18 = self._round_sar(isv18)
            inv.gravado_isv18 = self._round_sar(importe18)
    
    @api.depends(
        'invoice_line_ids.price_subtotal',
        'invoice_line_ids.tax_ids',
        'invoice_line_ids.display_type',
        'move_type',
    )
    def _compute_base_imponible(self):
        """Base gravada: suma de price_subtotal en líneas con impuesto y no exentas/exoneradas."""
        for inv in self:
            if not inv.is_invoice(include_receipts=True):
                inv.base_imponible_total = 0.0
                continue
            base_imponible = 0.0
            for line in self._fiscal_invoice_lines(inv):
                if not line.tax_ids or self._fiscal_line_is_exempt(line) or self._fiscal_line_is_exonerated(line):
                    continue
                base_imponible += line.price_subtotal
            inv.base_imponible_total = self._round_sar(base_imponible)
    
    @api.depends('amount_isv15', 'amount_isv18')
    def _compute_isv_total(self):
        """Calcular ISV total"""
        for inv in self:
            inv.isv_total = self._round_sar(inv.amount_isv15 + inv.amount_isv18)
    
    @api.depends('amount_total')
    def _compute_requires_fiscal_numbering(self):
        """Determinar si requiere numeración fiscal según SAR"""
        for inv in self:
            # Según SAR: Facturas menores a L. 500 no requieren numeración fiscal
            if inv.move_type in ['out_invoice', 'out_refund']:
                inv.requires_fiscal_numbering = inv.amount_total >= 500.0
            else:
                inv.requires_fiscal_numbering = False
    
    def _round_sar(self, amount):
        """Redondeo según SAR de Honduras (redondeo matemático a 2 decimales)"""
        return round(amount, 2)
    
    def _validate_fiscal_amounts(self):
        """Validar montos según requerimientos del SAR"""
        for inv in self:
            if inv.move_type in ['out_invoice', 'out_refund']:
                # Omitir validaciones fiscales para importaciones históricas
                if inv.is_import:
                    _logger.info("Omitiendo validaciones fiscales para movimiento %s - es importación histórica", inv.id)
                    continue

                # Las líneas sin impuesto reciben ISV 15% automáticamente en
                # ``_apply_fiscal_default_taxes`` (llamado antes de publicar),
                # por lo que aquí ya no se bloquea la factura.

                # Validar monto mínimo para facturación fiscal
                if inv.amount_total < 500.0 and inv.requires_fiscal_numbering:
                    raise ValidationError(_('Facturas menores a L. 500 no requieren numeración fiscal'))
                
                # Validar que los montos sean positivos
                if inv.amount_total < 0:
                    raise ValidationError(_('El monto total no puede ser negativo'))
                
                # Validar que ISV sea correcto
                calculated_isv = inv.amount_isv15 + inv.amount_isv18
                if abs(calculated_isv - inv.isv_total) > 0.01:
                    raise ValidationError(_('El ISV total no coincide con la suma de ISV 15% y 18%'))
    
    def validate_fiscal_invoice(self):
        """Validar factura fiscal completa"""
        for inv in self:
            try:
                # Omitir validaciones fiscales para importaciones históricas
                if inv.is_import:
                    _logger.info("Omitiendo validación fiscal completa para movimiento %s - es importación histórica", inv.id)
                    inv.fiscal_validation_status = 'validated'
                    inv.fiscal_validation_message = _('Documento importado del historial - validación fiscal omitida')
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Documento Importado'),
                            'message': _('El documento ha sido marcado como importación histórica.'),
                            'type': 'info',
                        }
                    }
                
                # Validar montos
                inv._validate_fiscal_amounts()
                
                # Validar campos obligatorios
                if inv.move_type in ['out_invoice', 'out_refund']:
                    if not inv.commercial_partner_id.vat and inv.commercial_partner_id.country_id.code == 'HN':
                        raise ValidationError(_('El cliente debe tener RTN válido'))
                    
                    if inv.requires_fiscal_numbering and not inv.cai:
                        raise ValidationError(_('Facturas que requieren numeración fiscal deben tener CAI'))
                
                # Marcar como validada
                inv.fiscal_validation_status = 'validated'
                inv.fiscal_validation_message = _('Factura validada correctamente')
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Factura Válida'),
                        'message': _('La factura ha sido validada correctamente.'),
                        'type': 'success',
                    }
                }
                
            except ValidationError as e:
                inv.fiscal_validation_status = 'error'
                inv.fiscal_validation_message = str(e)
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error de Validación'),
                        'message': str(e),
                        'type': 'danger',
                    }
                }

    @api.depends("sale_order_count")
    def _get_saleorder(self):
        for move in self:
            move.sale_order_id = move.line_ids.sale_line_ids.order_id

    def _sequence_matches_date(self):
        """Desactiva el control de fecha de Odoo para la numeración fiscal SAR.

        El correlativo lo gobierna el CAI/SAR, no el calendario de Odoo. El
        formato real de Honduras (``000-001-01-00000001``:
        establecimiento-punto de emisión-tipo de documento-correlativo) no
        lleva año, pero Odoo intenta deducir año/mes del propio número; si "no
        coincide" con la fecha de la factura, dispara ``_set_next_sequence``
        (que reasigna ``name`` a "/") o el constraint
        ``_constrains_date_sequence``. Esto se hace evidente, p. ej., con un CAI
        que cruza de año o con grupos de dígitos que Odoo confunde con un año.
        Para movimientos con numeración fiscal SAR devolvemos siempre True.
        """
        self.ensure_one()
        if (
            not self.is_import
            and self.journal_id
            and self.journal_id.needs_fiscal_sequence(self.move_type)
        ):
            sequence = self.journal_id.get_fiscal_sequence(self.move_type)
            if sequence and sequence.is_fiscal:
                return True
        return super()._sequence_matches_date()

    def _set_next_sequence(self):
        """
        Sobrescribimos _set_next_sequence para manejar secuencias fiscales.
        - Para secuencias fiscales (is_fiscal = True): Asignar "/" temporalmente
        - Para secuencias no fiscales: Comportamiento normal de Odoo
        - Para importaciones históricas: Omitir generación de correlativo fiscal
        """
        for move in self:
            # ✅ CONDICIÓN: Omitir generación de correlativo para importaciones históricas
            if move.is_import:
                _logger.info("Omitiendo generación de correlativo fiscal para movimiento %s - es importación histórica", move.id)
                # Para importaciones históricas, usar comportamiento normal de Odoo sin secuencia fiscal
                super(AccountMove, move)._set_next_sequence()
                continue
            
            # ✅ CONDICIÓN PRINCIPAL: Solo procesar si el diario necesita secuencia fiscal
            if not move.journal_id or not move.journal_id.needs_fiscal_sequence(move.move_type):
                # Para diarios que no requieren secuencia fiscal, usar comportamiento normal de Odoo
                super(AccountMove, move)._set_next_sequence()
                _logger.debug("Diario no requiere secuencia fiscal para movimiento %s - usando comportamiento normal de Odoo", move.id)
                continue

            # ✅ OBTENER SECUENCIA FISCAL APROPIADA
            sequence = move.journal_id.get_fiscal_sequence(move.move_type)
            if not sequence:
                # Si no hay secuencia fiscal configurada, usar comportamiento normal de Odoo
                super(AccountMove, move)._set_next_sequence()
                _logger.debug("No hay secuencia fiscal configurada para movimiento %s - usando comportamiento normal de Odoo", move.id)
                continue
            
            # ✅ LÓGICA: Solo el campo is_fiscal determina el comportamiento
            if sequence.is_fiscal:
                # Para secuencias fiscales, asignar "/" temporalmente
                # El número real se asignará en _post
                move.name = "/"
                _logger.debug("Secuencia fiscal detectada para movimiento %s - asignando '/' temporalmente", move.id)
            else:
                # Para secuencias no fiscales, usar el comportamiento normal de Odoo
                super(AccountMove, move)._set_next_sequence()
                _logger.debug("Secuencia no fiscal para movimiento %s - usando comportamiento normal de Odoo", move.id)

    @api.model
    def _is_model_installed(self, model_name):
        """True si el modelo está registrado (módulo opcional instalado)."""
        return model_name in self.env.registry

    def _is_stock_valuation_move(self):
        """True si el asiento proviene de valoración de inventario (stock_account)."""
        self.ensure_one()
        if not self.id or not self._is_model_installed('stock.valuation.layer'):
            return False
        return bool(self.env['stock.valuation.layer'].sudo().search(
            [('account_move_id', '=', self.id)], limit=1,
        ))

    def _is_payment_move(self):
        """True si el asiento está vinculado a un pago."""
        self.ensure_one()
        if self.payment_reference:
            return True
        if self.move_type != 'entry':
            return False
        line_model = self.env['account.move.line']
        if 'payment_id' not in line_model._fields:
            return False
        return bool(self.line_ids.filtered('payment_id'))

    def _fiscal_company_default_journal(self):
        """Diario configurado en la compañía para el move_type actual."""
        self.ensure_one()
        company = self.company_id or self.env.company
        move_type = self.move_type or self.env.context.get('default_move_type')
        journal_by_type = {
            'out_invoice': company.fiscal_default_sale_journal_id,
            'out_refund': company.fiscal_default_sale_refund_journal_id,
            'in_invoice': company.fiscal_default_purchase_journal_id,
            'in_refund': company.fiscal_default_purchase_refund_journal_id,
            'entry': company.fiscal_default_misc_journal_id,
        }
        journal = journal_by_type.get(move_type)
        if not journal:
            return self.env['account.journal']
        valid_types = self._get_valid_journal_types()
        if journal.type not in valid_types:
            return self.env['account.journal']
        return journal

    def _search_default_journal(self):
        self.ensure_one()
        fiscal_journal = self._fiscal_company_default_journal()
        if fiscal_journal:
            return fiscal_journal
        return super()._search_default_journal()

    def _should_skip_fiscal_assignment(self):
        """Movimientos que no deben recibir correlativo SAR."""
        self.ensure_one()
        if self.is_import:
            return True
        if self._is_stock_valuation_move():
            return True
        if self._is_payment_move():
            return True
        if 'statement_line_id' in self._fields and self.statement_line_id:
            return True
        if self.move_type in ('entry', 'out_invoice', 'in_invoice') and not self.invoice_line_ids:
            return True
        return False

    def _should_apply_sar_fiscal_number(self):
        """True si el movimiento debe recibir correlativo y datos SAR."""
        self.ensure_one()
        if self.state != 'draft':
            _logger.info(
                "FISCAL DEBUG: factura %s omitida — state=%s (no draft)",
                self.id, self.state,
            )
            return False
        if self._should_skip_fiscal_assignment():
            _logger.info(
                "FISCAL DEBUG: factura %s omitida — _should_skip_fiscal_assignment",
                self.id,
            )
            return False
        if not self.journal_id.needs_fiscal_sequence(self.move_type):
            _logger.info(
                "FISCAL DEBUG: factura %s omitida — diario sin secuencia fiscal "
                "(document_fiscal=%s)",
                self.id, self.journal_id.document_fiscal,
            )
            return False
        sequence = self.journal_id.get_fiscal_sequence(self.move_type)
        if not sequence or not sequence.is_fiscal:
            _logger.info(
                "FISCAL DEBUG: factura %s omitida — secuencia fiscal no configurada "
                "(fiscal_sequence_id=%s, is_fiscal=%s)",
                self.id,
                self.journal_id.fiscal_sequence_id.id,
                sequence.is_fiscal if sequence else None,
            )
            return False
        if self.cai:
            _logger.info(
                "FISCAL DEBUG: factura %s omitida — ya tiene CAI=%s",
                self.id, self.cai,
            )
            return False
        return True

    @staticmethod
    def _sanitize_fiscal_name(value):
        """Elimina saltos de línea/caracteres de control de un correlativo fiscal.

        Odoo separa el `name` en prefijo/número con una regex cuyo comodín `.`
        no admite saltos de línea. Un prefijo o sufijo de la secuencia con un
        `\\n` embebido (p. ej. pegado desde un PDF) genera un nombre inválido y
        rompe `_compute_split_sequence`. Saneamos el valor antes de escribirlo.
        """
        if not value:
            return value
        return _FISCAL_NAME_INVALID_CHARS_RE.sub('', value).strip()

    def _assign_sar_fiscal_number(self, sequence):
        """Asigna correlativo SAR y datos CAI al movimiento (idealmente en borrador)."""
        self.ensure_one()
        move = self
        _logger.info(
            "FISCAL DEBUG: asignando correlativo SAR a factura %s, secuencia %s",
            move.id, sequence.display_name,
        )
        if sequence.use_date_range:
            date = move.invoice_date or move.date
            sequence_status = sequence.validate_sequence_continuity(date)
            _logger.info(
                "FISCAL DEBUG: continuidad secuencia=%s valid=%s can_continue=%s",
                sequence.name,
                sequence_status.get('valid'),
                sequence_status.get('can_continue'),
            )
            if not sequence_status['valid']:
                raise ValidationError(_(
                    'Error de validación fiscal para la secuencia %(seq)s: %(msg)s',
                    seq=sequence.name,
                    msg=sequence_status['message'],
                ))
            current_range = sequence_status.get('current_range')
            if not current_range:
                next_range = sequence.get_next_available_range(date)
                if next_range:
                    raise ValidationError(_(
                        'No hay rango fiscal vigente para la fecha %(date)s. '
                        'Existe un rango futuro desde %(future)s.',
                        date=date,
                        future=next_range.date_from,
                    ))
                raise ValidationError(_(
                    'No hay rangos fiscales válidos para la fecha %(date)s.',
                    date=date,
                ))
            if not sequence_status['can_continue'] and not sequence.has_valid_future_sequences(date):
                raise ValidationError(_(
                    'El rango fiscal actual está agotado y no hay subsecuencias futuras '
                    'para la secuencia %(seq)s.',
                    seq=sequence.name,
                ))
            if (
                hasattr(current_range, 'rangoFinal')
                and current_range.rangoFinal
                and current_range.number_next_actual > current_range.rangoFinal
                and not sequence.has_valid_future_sequences(date)
            ):
                raise ValidationError(_(
                    'El rango numérico fiscal %(start)s-%(end)s está agotado.',
                    start=current_range.rangoInicial,
                    end=current_range.rangoFinal,
                ))
            new_name = self._sanitize_fiscal_name(
                sequence.next_by_id(sequence_date=date)
            )
            vals_to_write = {
                'name': new_name,
                'cai': getattr(current_range, 'cai', '') or '',
                'fechaLimiteEmision': getattr(current_range, 'date_to', False) or False,
                'totalAmountString': self.numero_to_letras(move.amount_total),
            }
            if getattr(current_range, 'rangoInicial', None) and getattr(current_range, 'rangoFinal', None):
                vals_to_write.update({
                    'numeroInicial': self._sanitize_fiscal_name(
                        sequence.format_sequence_number(
                            current_range.rangoInicial, date, current_range,
                        )
                    ),
                    'numeroFinal': self._sanitize_fiscal_name(
                        sequence.format_sequence_number(
                            current_range.rangoFinal, date, current_range,
                        )
                    ),
                })
            move.write(vals_to_write)
            _logger.info(
                "FISCAL DEBUG: factura %s actualizada name=%s cai=%s rango=%s-%s",
                move.id, new_name, vals_to_write.get('cai'),
                vals_to_write.get('numeroInicial'), vals_to_write.get('numeroFinal'),
            )
            return

        new_name = self._sanitize_fiscal_name(
            sequence.next_by_id(sequence_date=move.date)
        )
        move.write({
            'name': new_name,
            'totalAmountString': self.numero_to_letras(move.amount_total),
        })
        _logger.info(
            "FISCAL DEBUG: factura %s actualizada name=%s (sin rango de fechas)",
            move.id, new_name,
        )

    def _check_categorias_productos_validadas(self):
        """Bloquea publicar facturas con productos de categoría no validada.

        Reutiliza la validación de ``product.template`` (estado distinto de
        'ok'): exige que la categoría tenga la configuración contable mínima
        y la validación humana de Contabilidad.
        """
        errores = []
        for move in self:
            if move.is_import or not move.is_invoice(include_receipts=True):
                continue
            productos = move.invoice_line_ids.filtered(
                lambda line: not line.display_type and line.product_id
            ).mapped('product_id.product_tmpl_id')
            for producto in productos:
                error = producto._fiscal_categoria_validacion_error()
                if error:
                    errores.append(error)
        if errores:
            raise ValidationError(
                _("No se puede confirmar la factura.\n\n")
                + "\n\n".join(dict.fromkeys(errores))
            )

    def _post(self, soft=True):
        """
        Publica movimientos y asigna correlativo SAR antes del post nativo,
        para que Odoo no asigne INV/ y los datos SAR queden en la factura.
        """
        # Bloquea publicar facturas con productos cuya categoría no esté
        # validada por Contabilidad (no_valida / pendiente).
        self._check_categorias_productos_validadas()

        # Auto-aplica ISV 15% a líneas sin impuesto y sustituye por Exonerado
        # 0% en facturas exoneradas, antes de validar y publicar.
        self._apply_fiscal_default_taxes()

        for move in self:
            if move.move_type in ('out_invoice', 'out_refund') and not move.is_import:
                try:
                    move._validate_fiscal_amounts()
                except ValidationError as error:
                    move.fiscal_validation_status = 'error'
                    move.fiscal_validation_message = str(error)
                    raise

        for move in self:
            _logger.info("=== FISCAL DEBUG: Procesando factura %s ===", move.id)
            _logger.info(
                "FISCAL DEBUG: move_type=%s state=%s name=%s",
                move.move_type, move.state, move.name,
            )
            _logger.info(
                "FISCAL DEBUG: journal needs_fiscal=%s document_fiscal=%s",
                move.journal_id.needs_fiscal_sequence(move.move_type),
                move.journal_id.document_fiscal,
            )
            sequence = move.journal_id.get_fiscal_sequence(move.move_type)
            _logger.info(
                "FISCAL DEBUG: fiscal_sequence=%s (id=%s, is_fiscal=%s)",
                sequence.display_name if sequence else None,
                sequence.id if sequence else None,
                sequence.is_fiscal if sequence else None,
            )
            if not move._should_apply_sar_fiscal_number():
                continue
            move._assign_sar_fiscal_number(sequence)

        self._validate_compra_dmc()

        posted = super()._post(soft)
        return posted

    @api.depends('amount_total', 'currency_id')
    def _compute_amount_words(self) -> None:
        """Calcula el monto total en letras usando NumberUtilities."""
        for move in self:
            if move.amount_total:
                move.amount_words = _num_util.numero_to_letras(move.amount_total)
            else:
                move.amount_words = ''

    def letra_cifra(self):
        for r in self:
            r.totalAmountString = self.numero_to_letras(r.amount_total)
        return self

    def numero_to_letras(self, numero: float) -> str:
        """Delega la conversión numérica a letras a NumberUtilities."""
        return _num_util.numero_to_letras(numero)

    @api.model
    def _split_printable_report_pages(
        self, line_list, recordset, first_cap=9, middle_cap=10, last_cap=7, single_cap=7,
    ):
        """Parte líneas de reporte PDF según cupo por tipo de página.

        En factura el encabezado se repite en cada hoja, por eso los cupos son bajos.
        ``single_cap`` / ``last_cap`` reservan espacio a totales+CAI.
        """
        n = len(line_list)
        empty = recordset.browse()
        if not n:
            return [empty]

        def _browse(chunk):
            return recordset.browse([line.id for line in chunk])

        if n <= single_cap:
            return [_browse(line_list)]

        pages = []
        idx = 0
        is_first = True
        while idx < n:
            rem = n - idx
            if is_first:
                # Evitar 2.ª página con 1–2 líneas: absorber en la 1.ª (soft).
                if rem <= first_cap + 2:
                    pages.append(_browse(line_list[idx:]))
                    break
                take = first_cap
                is_first = False
            else:
                # Continuación / última: absorber remanente pequeño (evita huérfanas).
                if rem <= middle_cap + 3:
                    pages.append(_browse(line_list[idx:]))
                    break
                take = middle_cap
            pages.append(_browse(line_list[idx:idx + take]))
            idx += take
        return pages

    def _get_sar_invoice_report_pages(self):
        """Parte las líneas imprimibles de la factura SAR.

        Header SAR grande en cada hoja + bloque totales/CAI al final → cupos bajos
        para evitar vacíos por desborde (mismo problema que OV con cupo 26).
        Las secciones (line_section) no se imprimen.
        """
        self.ensure_one()
        lines = self.invoice_line_ids.filtered(
            lambda line: line.display_type in ('product', 'line_note')
        ).sorted(key=lambda line: (-line.sequence, line.date, line.move_name, -line.id), reverse=True)
        return self._split_printable_report_pages(
            list(lines),
            lines,
            first_cap=9,
            middle_cap=10,
            last_cap=7,
            single_cap=7,
        )

    @api.model
    def _sar_invoice_line_display_name(self, line):
        """Descripción comercial sin código interno [DEFAULT_CODE]."""
        name = (line.name or '').strip()
        if name.startswith('['):
            end = name.find(']')
            if end > 1:
                name = name[end + 1:]
        return '\n'.join(
            part.strip() for part in name.splitlines() if part.strip()
        )

    @api.depends_context('uid')
    def _compute_fiscal_can_manage_cancel(self):
        is_fiscal_admin = self.env.user.has_group(
            'kc_fiscal_hn_v18.group_fiscal_sequence_manager'
        )
        for move in self:
            move.fiscal_can_manage_cancel = is_fiscal_admin

    @api.depends('state', 'journal_id', 'move_type', 'invoice_date', 'date')
    def _compute_fiscal_can_confirm(self):
        """False si la fecha o el rango fiscal ha vencido y no hay subsecuencias futuras (ocultar Confirmar)."""
        for move in self:
            if move.state != 'draft':
                move.fiscal_can_confirm = True
                continue
            if not move.journal_id or not move.journal_id.needs_fiscal_sequence(move.move_type):
                move.fiscal_can_confirm = True
                continue
            if move.is_import:
                move.fiscal_can_confirm = True
                continue
            if not getattr(move.journal_id, 'get_fiscal_sequence', None):
                move.fiscal_can_confirm = True
                continue
            sequence = move.journal_id.get_fiscal_sequence(move.move_type)
            if not sequence or not getattr(sequence, 'is_fiscal', False) or not getattr(sequence, 'use_date_range', False):
                move.fiscal_can_confirm = True
                continue
            date = move.invoice_date or move.date
            if not date:
                move.fiscal_can_confirm = True
                continue
            if not getattr(sequence, 'validate_sequence_continuity', None):
                move.fiscal_can_confirm = True
                continue
            sequence_status = sequence.validate_sequence_continuity(date)
            if not sequence_status or not sequence_status.get('valid'):
                move.fiscal_can_confirm = True
                continue
            current_range = sequence_status.get('current_range')
            if not current_range:
                future_range = getattr(sequence, 'get_next_available_range', None) and sequence.get_next_available_range(date)
                move.fiscal_can_confirm = bool(future_range)
                continue
            if not sequence_status.get('can_continue', True):
                has_future = getattr(sequence, 'has_valid_future_sequences', None) and sequence.has_valid_future_sequences(date)
                move.fiscal_can_confirm = bool(has_future)
                continue
            # Revisar fecha límite vencida (independiente del umbral de alerta)
            if getattr(current_range, 'date_to', None):
                dias_restantes = (current_range.date_to - fields.Date.today()).days
                if dias_restantes <= 0:
                    future_ranges = getattr(sequence, 'get_available_future_ranges', None) and sequence.get_available_future_ranges(date)
                    move.fiscal_can_confirm = bool(future_ranges)
                    continue
            # Revisar rango numérico agotado
            if getattr(current_range, 'rangoInicial', None) is not None and getattr(current_range, 'rangoFinal', None) is not None:
                number_next = getattr(current_range, 'number_next_actual', current_range.rangoInicial)
                numeros_restantes = current_range.rangoFinal - number_next + 1
                if numeros_restantes <= 0:
                    future_ranges = getattr(sequence, 'get_available_future_ranges', None) and sequence.get_available_future_ranges(date)
                    move.fiscal_can_confirm = bool(future_ranges)
                    continue
            move.fiscal_can_confirm = True

    def _get_fiscal_post_warning_action(self, alert, move):
        """Abre wizard de advertencia fiscal (no bloqueante)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.warning.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_warning_message': alert['message'],
                'default_move_id': move.id,
                'default_warning_type': alert.get('type', 'general'),
                'active_id': move.id,
                'active_model': 'account.move',
            },
        }

    def _check_exoneracion_al_facturar(self):
        """Valida la vigencia del acuerdo de exoneración del cliente.

        Se dispara solo en facturas/notas de crédito de venta que aplican
        impuesto exonerado. Devuelve la acción del wizard de advertencia
        cuando corresponde, o lanza UserError en modo bloqueo duro (salvo que
        el usuario sea Gerente fiscal). Devuelve None si todo está correcto.
        """
        self.ensure_one()
        if self.move_type not in ('out_invoice', 'out_refund'):
            return None
        if self.is_import:
            return None

        company = self.company_id or self.env.company
        modo = company.exoneracion_modo_control
        if modo == 'ninguno':
            return None

        # Solo aplica cuando la factura lleva impuesto exonerado.
        if not self.amount_exonerado or self.amount_exonerado <= 0:
            return None

        partner = self.commercial_partner_id or self.partner_id
        fecha_doc = (
            self.invoice_date or self.date
            or fields.Date.context_today(self)
        )

        motivo = False
        if not partner.tiene_exoneracion_sar:
            motivo = _(
                'La factura aplica impuesto exonerado pero el cliente '
                '%(nombre)s no tiene una exoneración SAR registrada.',
                nombre=partner.name,
            )
        elif not partner.fecha_vencimiento_exoneracion:
            motivo = _(
                'El cliente %(nombre)s tiene exoneración marcada pero sin '
                'fecha de vencimiento registrada; no se considera vigente.',
                nombre=partner.name,
            )
        elif partner.fecha_vencimiento_exoneracion < fecha_doc:
            motivo = _(
                'El acuerdo de exoneración del cliente %(nombre)s venció el '
                '%(fecha)s (fecha del documento: %(doc)s).',
                nombre=partner.name,
                fecha=partner.fecha_vencimiento_exoneracion,
                doc=fecha_doc,
            )

        if not motivo:
            return None

        es_gerente = self.env.user.has_group(
            'kc_fiscal_hn_v18.group_fiscal_sequence_manager'
        )
        if modo == 'bloqueo' and not es_gerente:
            raise UserError(
                '%s\n\n%s' % (
                    motivo,
                    _('No es posible confirmar la factura con un acuerdo de '
                      'exoneración vencido o inválido. Actualice la '
                      'exoneración del cliente o contacte al Gerente fiscal.'),
                )
            )

        _logger.warning(
            "Alerta exoneración factura %s cliente %s: %s",
            self.id, partner.id, motivo,
        )
        return self._get_fiscal_post_warning_action(
            {'message': motivo, 'type': 'exoneracion'}, self,
        )

    def action_post(self):
        for move in self:
            if move.move_type == 'out_invoice':
                move.company_id.check_consumidor_final_limit(
                    move.partner_id, move.amount_total,
                    move.currency_id, move,
                )

        if not self.env.context.get('skip_fiscal_warning'):
            for move in self:
                warning_action = move._check_exoneracion_al_facturar()
                if warning_action:
                    return warning_action

        for move in self:
            if self.env.context.get('skip_fiscal_warning'):
                continue
            if move.is_import or not move.journal_id.needs_fiscal_sequence(move.move_type):
                continue
            sequence = move.journal_id.get_fiscal_sequence(move.move_type)
            if not sequence or not sequence.is_fiscal or not sequence.use_date_range:
                continue

            document_date = move.invoice_date or move.date
            for alert in sequence.get_fiscal_post_alerts(document_date):
                if alert.get('blocking'):
                    raise UserError(alert['message'])
                _logger.warning(
                    "Alerta fiscal %s secuencia %s factura %s: %s",
                    alert.get('type'), sequence.name, move.id, alert['message'],
                )
                return move._get_fiscal_post_warning_action(alert, move)

        return super().action_post()

    def _get_name_invoice_report(self):
        """
        Sobrescribir para mostrar el correlativo del proveedor en el nombre del reporte
        para facturas y notas de crédito de proveedor
        """
        self.ensure_one()
        
        if self.move_type in ['in_invoice', 'in_refund']:
            # Para facturas y notas de crédito de proveedor
            if self.correlativo_proveedor:
                # Concatenar el nombre del documento con el correlativo del proveedor
                return f"{self.correlativo_proveedor} - {self.name}"
            else:
                return self.name
        else:
            # Para otros tipos de documentos, comportamiento normal
            return super()._get_name_invoice_report()

    @api.depends('name', 'correlativo_proveedor', 'move_type')
    def _compute_display_name(self) -> None:
        """Muestra correlativo del proveedor en facturas de compra."""
        super()._compute_display_name()
        for move in self:
            if move.move_type in ('in_invoice', 'in_refund') and move.correlativo_proveedor:
                move.display_name = f"{move.correlativo_proveedor} - {move.name}"

    @api.depends("name", "correlativo_proveedor")
    def _compute_referencia_completa(self):
        for move in self:
            if move.move_type in ['in_invoice', 'in_refund'] and move.correlativo_proveedor:
                move.referencia_completa = f"{move.correlativo_proveedor} - {move.name}"
            else:
                move.referencia_completa = move.name or ''

    def marcar_como_importacion_historica(self):
        """
        Método helper para marcar documentos como importación histórica
        Útil para procesos de importación masiva
        """
        self.ensure_one()
        self.write({'is_import': True})
        _logger.info("Documento %s marcado como importación histórica", self.name)
        return True

    @api.model
    def crear_documento_historico(self, vals):
        """
        Método helper para crear documentos históricos sin correlativo fiscal
        """
        # Asegurar que el documento se marque como importación histórica
        vals['is_import'] = True
        
        # Crear el documento
        documento = self.create(vals)
        
        _logger.info("Documento histórico creado: %s (ID: %s)", documento.name, documento.id)
        return documento

# class AccountMoveLineExtended(models.Model):
#     _inherit = 'account.move.line'

#     analytic_distribution_text = fields.Char(string='Distribución Analítica',
#                                              compute='get_name_analytic_distribution')

#     @api.depends("analytic_distribution")
#     def get_name_analytic_distribution(self):
#         for r in self:
#             r.analytic_distribution_text = ""
#             if r.analytic_distribution:
#                 for ad in r.analytic_distribution:
#                     analytic = self.env['account.analytic.account'].search(
#                         [('id', '=', ad)])
#                     if r.analytic_distribution_text == False:
#                         r.analytic_distribution_text = ""
#                         r.analytic_distribution_text = str(analytic.name)
#                     else:
#                         r.analytic_distribution_text = str(
#                             r.analytic_distribution_text) + ", " + str(analytic.name)
#                         print(r.analytic_distribution_text)

