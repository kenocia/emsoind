# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)

SAR_PRINT_MIGRATION_VERSION = '1'
SAR_PRINT_MIGRATION_PARAM = 'kc_fiscal_hn.sar_print_migration_version'


def _journal_has_column(cr, column_name):
    cr.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'account_journal'
          AND column_name = %s
    """, (column_name,))
    return bool(cr.fetchone())


def _migrate_sar_journal_sequences(env):
    """Migrar secuencias SAR desde sequence_id nativo a fiscal_sequence_id."""
    cr = env.cr
    if not _journal_has_column(cr, 'fiscal_sequence_id'):
        return

    if _journal_has_column(cr, 'sequence_id'):
        cr.execute("""
            SELECT aj.id, aj.sequence_id, aj.refund_sequence_id, aj.document_fiscal
            FROM account_journal aj
            WHERE aj.document_fiscal IS NOT NULL
              AND aj.fiscal_sequence_id IS NULL
              AND aj.sequence_id IS NOT NULL
        """)
        rows = cr.fetchall()
        if rows:
            Sequence = env['ir.sequence']
            Journal = env['account.journal']
            migrated = 0

            for journal_id, sequence_id, refund_sequence_id, document_fiscal in rows:
                vals = {}
                seq = Sequence.browse(sequence_id)
                if seq.exists() and seq.is_fiscal:
                    vals['fiscal_sequence_id'] = sequence_id
                if refund_sequence_id:
                    refund_seq = Sequence.browse(refund_sequence_id)
                    if refund_seq.exists() and refund_seq.is_fiscal:
                        vals['refund_fiscal_sequence_id'] = refund_sequence_id
                if vals:
                    Journal.browse(journal_id).write(vals)
                    migrated += 1
                    _logger.info(
                        'Diario %s: migrada secuencia fiscal SAR a fiscal_sequence_id',
                        journal_id,
                    )

            if migrated:
                _logger.info(
                    'Migración SAR: %d diario(s) actualizados con fiscal_sequence_id.',
                    migrated,
                )
    else:
        _logger.info(
            'SAR: account.journal sin sequence_id nativo; '
            'migración de secuencias omitida.',
        )

    Journal = env['account.journal']
    fiscal_defaults = (
        ('purchase', 'vendors'),
        ('sale', 'client'),
    )
    for journal_type, doc_fiscal in fiscal_defaults:
        journals = Journal.search([
            ('type', '=', journal_type),
            ('document_fiscal', '=', False),
        ])
        if journals:
            journals.write({'document_fiscal': doc_fiscal})
            _logger.info(
                'SAR: %d diario(s) %s → document_fiscal=%s',
                len(journals), journal_type, doc_fiscal,
            )


def configure_fiscal_journal_default_accounts(env):
    """
    Configura cuentas por defecto en los diarios fiscales HN.
    No falla si no encuentra las cuentas.
    """
    company = env.company

    def buscar_cuenta(codigos, tipos_cuenta=None):
        Account = env['account.account']
        domain_base = [('company_ids', 'in', [company.id])]
        for codigo in codigos:
            cuenta = Account.search(
                domain_base + [('code', 'like', codigo + '%')],
                limit=1,
            )
            if cuenta:
                return cuenta
        if tipos_cuenta:
            return Account.search(
                domain_base + [('account_type', 'in', tipos_cuenta)],
                limit=1,
            )
        return False

    sale_tipos = ['income', 'income_other']
    purchase_tipos = ['expense', 'expense_direct_cost', 'expense_depreciation']

    cuentas_por_diario = {
        'VEN': buscar_cuenta(
            ['4101', '4.1', '4.', '1101', '1100', '110'],
            sale_tipos,
        ),
        'NCC': buscar_cuenta(
            ['4101', '4.1', '4.', '1101', '1100', '110'],
            sale_tipos,
        ),
        'NDC': buscar_cuenta(
            ['4101', '4.1', '4.', '1101', '1100', '110'],
            sale_tipos,
        ),
        'CFA': buscar_cuenta(
            ['6101', '6.1', '6.', '2101', '2100', '210'],
            purchase_tipos,
        ),
        'BOL': buscar_cuenta(
            ['6101', '6.1', '6.', '2101', '2100', '210'],
            purchase_tipos,
        ),
        'IMP': buscar_cuenta(
            ['6101', '6.1', '6.', '2101', '2100', '210'],
            purchase_tipos,
        ),
        'NCP': buscar_cuenta(
            ['6101', '6.1', '6.', '2101', '2100', '210'],
            purchase_tipos,
        ),
        'RET': buscar_cuenta(
            ['2103', '2105', '2.1.03', '2.1.02', '210', '6101', '6.1'],
            purchase_tipos + ['liability_current'],
        ),
    }

    for codigo_diario, cuenta in cuentas_por_diario.items():
        diario = env['account.journal'].search([
            ('code', '=', codigo_diario),
            ('company_id', '=', company.id),
        ], limit=1)
        if not diario:
            continue
        if cuenta and not diario.default_account_id:
            try:
                diario.write({'default_account_id': cuenta.id})
                _logger.info(
                    'Diario %s → cuenta %s asignada',
                    codigo_diario, cuenta.code,
                )
            except Exception as exc:
                _logger.warning(
                    'Diario %s → no se pudo asignar cuenta %s: %s',
                    codigo_diario, cuenta.code, exc,
                )
        else:
            _logger.info(
                'Diario %s → sin cambios',
                codigo_diario,
            )


def migrate_sar_print_count(env):
    """Inicializa sar_print_count=1 en ventas fiscales ya publicadas (original asumido)."""
    icp = env['ir.config_parameter'].sudo()
    if icp.get_param(SAR_PRINT_MIGRATION_PARAM) == SAR_PRINT_MIGRATION_VERSION:
        return
    if 'sar_print_count' not in env['account.move']._fields:
        return
    moves = env['account.move'].search([
        ('state', '=', 'posted'),
        ('move_type', '=', 'out_invoice'),
        ('journal_id.document_fiscal', '=', 'client'),
        ('sar_print_count', '=', 0),
    ])
    if moves:
        moves.with_context(sar_print_internal=True).write({'sar_print_count': 1})
        _logger.info(
            'Migración impresión SAR v%s: %d factura(s) marcadas con '
            'sar_print_count=1 (original asumido entregado).',
            SAR_PRINT_MIGRATION_VERSION,
            len(moves),
        )
    icp.set_param(SAR_PRINT_MIGRATION_PARAM, SAR_PRINT_MIGRATION_VERSION)


def _normalize_fiscal_sequence_codes(env):
    """Elimina espacios/saltos de línea en code y name de secuencias fiscales."""
    env['ir.sequence']._init_normalize_fiscal_codes()


def _find_company_journal(env, company, *, codes=(), journal_type=None, document_fiscal=None):
    """Busca un diario por código preferido o por tipo/documento fiscal."""
    Journal = env['account.journal']
    for code in codes:
        journal = Journal.search([
            ('company_id', '=', company.id),
            ('code', '=', code),
        ], limit=1)
        if journal:
            return journal
    domain = [('company_id', '=', company.id)]
    if journal_type:
        domain.append(('type', '=', journal_type))
    if document_fiscal:
        domain.append(('document_fiscal', '=', document_fiscal))
    return Journal.search(domain, order='sequence, id', limit=1)


def remove_account_move_journal_ir_default(env):
    """Elimina defaults globales de journal_id que pisan la lógica por vista."""
    field = env['ir.model.fields'].search([
        ('model', '=', 'account.move'),
        ('name', '=', 'journal_id'),
    ], limit=1)
    if not field:
        return 0
    defaults = env['ir.default'].sudo().search([('field_id', '=', field.id)])
    if defaults:
        _logger.info(
            'SAR: eliminando %d valor(es) por defecto global(es) en '
            'account.move.journal_id.',
            len(defaults),
        )
        defaults.unlink()
    return len(defaults)


def configure_account_move_company_journal_defaults(env):
    """Asigna diarios por defecto por compañía si aún no están configurados."""
    Company = env['res.company']
    if 'fiscal_default_sale_journal_id' not in Company._fields:
        return

    journal_specs = {
        'fiscal_default_sale_journal_id': {
            'codes': ('INV', 'FCSPS', 'VEN'),
            'journal_type': 'sale',
            'document_fiscal': 'client',
        },
        'fiscal_default_sale_refund_journal_id': {
            'codes': ('NCC',),
            'journal_type': 'sale',
            'document_fiscal': 'credit',
        },
        'fiscal_default_purchase_journal_id': {
            'codes': ('FACTU', 'CFA'),
            'journal_type': 'purchase',
            'document_fiscal': 'vendors',
        },
        'fiscal_default_purchase_refund_journal_id': {
            'codes': ('NCP',),
            'journal_type': 'purchase',
            'document_fiscal': 'credit',
        },
        'fiscal_default_misc_journal_id': {
            'codes': ('MISCE',),
            'journal_type': 'general',
            'document_fiscal': None,
        },
    }

    for company in Company.search([]):
        vals = {}
        for field_name, spec in journal_specs.items():
            if company[field_name]:
                continue
            journal = _find_company_journal(
                env,
                company,
                codes=spec['codes'],
                journal_type=spec['journal_type'],
                document_fiscal=spec['document_fiscal'],
            )
            if journal:
                vals[field_name] = journal.id
        if vals:
            company.write(vals)
            _logger.info(
                'SAR: compañía %s → diarios por defecto: %s',
                company.display_name,
                ', '.join(f'{k}={v}' for k, v in vals.items()),
            )


def post_init_hook(env):
    """Hook post-instalación: migración SAR y cuentas en diarios fiscales."""
    _migrate_sar_journal_sequences(env)
    _normalize_fiscal_sequence_codes(env)
    configure_fiscal_journal_default_accounts(env)
    remove_account_move_journal_ir_default(env)
    configure_account_move_company_journal_defaults(env)
    migrate_sar_print_count(env)
