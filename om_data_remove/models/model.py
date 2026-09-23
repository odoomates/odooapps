import logging

import psycopg2
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.sql_db import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

# The transactions of the standard Odoo 20 applications: the documents a company records day after day.
# The master data they point to (partners, products, chart of accounts, journals, taxes, employees, bills of
# materials, projects, configuration) is kept. The models of applications that are not installed are skipped.
# Within a group the lines come before their document, but the order does not have to be right: a table the
# database refuses to empty yet is tried again once the others are gone.
TRANSACTION_GROUPS = [
    ('accounting', 'Accounting and Payments', [
        'account.partial.reconcile', 'account.full.reconcile', 'account.move.line', 'account.payment',
        'account.bank.statement.line', 'account.bank.statement', 'account.move', 'account.analytic.line',
        'account.lock_exception', 'account.edi.document', 'payment.transaction',
    ]),
    ('sales', 'Sales', ['sale.order.line', 'sale.order']),
    ('pos', 'Point of Sale', ['pos.payment', 'pos.pack.operation.lot', 'pos.order.line', 'pos.order', 'pos.session']),
    ('purchase', 'Purchases', [
        'purchase.order.line', 'purchase.order', 'purchase.requisition.line', 'purchase.requisition',
    ]),
    ('inventory', 'Inventory', [
        'stock.valuation.adjustment.lines', 'stock.landed.cost.lines', 'stock.landed.cost',
        'stock.move.line', 'stock.move', 'stock.quant', 'stock.package', 'stock.picking', 'stock.picking.batch',
        'stock.lot', 'stock.reference',
    ]),
    ('mrp', 'Manufacturing', ['mrp.workcenter.productivity', 'mrp.workorder', 'mrp.unbuild', 'mrp.production']),
    ('hr', 'Employees', ['hr.expense', 'hr.leave', 'hr.leave.allocation', 'hr.attendance', 'hr.applicant']),
    ('crm', 'CRM', ['crm.lead']),
    ('project', 'Projects', ['project.update', 'project.task', 'project.task.recurrence']),
    ('repair', 'Repairs', ['repair.order']),
    ('maintenance', 'Maintenance', ['maintenance.request']),
    ('fleet', 'Fleet', ['fleet.vehicle.log.services', 'fleet.vehicle.log.contract', 'fleet.vehicle.odometer']),
    ('event', 'Events', ['event.registration']),
    ('survey', 'Surveys', ['survey.user_input.line', 'survey.user_input']),
    ('marketing', 'Email and SMS Marketing', ['mailing.trace', 'sms.sms', 'mail.mail']),
    ('website', 'Website', ['website.track', 'website.visitor']),
    ('lunch', 'Lunch', ['lunch.order', 'lunch.cashmove']),
    ('loyalty', 'Loyalty', ['loyalty.history', 'loyalty.card']),
    ('calendar', 'Calendar', ['calendar.attendee', 'calendar.event']),
    # every message and activity goes, on the kept records too: the chatter starts empty
    ('chatter', 'Discuss and Chatter', ['mail.activity', 'mail.message']),
]
# the records attached to a document by its model name: they go with the documents they belong to
LINKED_TABLES = [
    ('mail_message', 'model'),
    ('mail_followers', 'res_model'),
    ('mail_activity', 'res_model'),
    ('ir_attachment', 'res_model'),
    ('rating_rating', 'res_model'),
    ('ir_model_data', 'model'),
]
# the numbering of the cleared documents, which starts again from 1
SEQUENCE_CODES = [
    'sale.order', 'purchase.order', 'purchase.requisition.blanket.order', 'purchase.requisition.purchase.template',
    'account.payment', 'stock.picking', 'picking.batch', 'stock.lot.serial', 'stock.package', 'stock.landed.cost',
    'mrp.production', 'mrp.unbuild', 'repair_operation', 'pos.order', 'pos.session', 'hr.expense', 'lunch.order',
]
# the tables of the framework itself: emptying them would break the database, so they are never offered
PROTECTED_TABLES = {
    'res_users', 'res_company', 'res_groups', 'res_lang', 'res_currency', 'res_country', 'res_country_state',
    'res_country_group', 'res_partner_title', 'res_bank', 'decimal_precision', 'report_paperformat',
}
PROTECTED_PREFIXES = ('ir_', 'res_users_', 'res_groups_', 'res_company_', 'res_currency_', 'bus_', 'om_data_remove')
# the tables of the framework and of the configuration, and the reference data that comes with the modules:
# they are not what a clearing is about, so the report of the database tables leaves them out of its list
FRAMEWORK_TABLES = PROTECTED_TABLES | {
    'res_city', 'res_partner_industry', 'res_config', 'res_config_settings', 'res_device', 'res_device_log',
    'report_layout', 'mail_message_subtype', 'mail_activity_type', 'mail_activity_plan', 'mail_activity_plan_template',
    'mail_template', 'mail_alias', 'mail_alias_domain', 'mail_guest', 'mail_link_preview', 'mail_message_link_preview',
    'mail_canned_response', 'mail_push', 'mail_push_device', 'mail_blacklist', 'mail_ice_server', 'mail_gateway_allowed',
    'phone_blacklist', 'discuss_call_history', 'discuss_gif_favorite', 'discuss_voice_metadata',
    'fetchmail_server', 'privacy_log', 'spreadsheet_revision', 'spreadsheet_dashboard_group', 'onboarding_onboarding',
    'onboarding_onboarding_step', 'onboarding_progress', 'onboarding_progress_step', 'res_users_settings_volumes',
    'mail_call_artifact', 'sale_pdf_form_field', 'properties_base_definition', 'portal_entry', 'calendar_filters',
    'calendar_alarm', 'hr_work_entry_type', 'hr_time_rule', 'payment_provider', 'payment_method', 'res_role',
    'event_type_mail', 'crm_recurring_plan', 'account_analytic_applicability',
}
FRAMEWORK_PREFIXES = PROTECTED_PREFIXES + (
    'res_lang', 'res_country', 'res_currency', 'res_groups', 'res_users', 'res_company', 'base_', 'web_', 'auth_',
    'iap_', 'digest_', 'utm_', 'l10n_', 'sms_template', 'snailmail_', 'html_editor_', 'google_', 'microsoft_',
    'discuss_', 'barcode_', 'website', 'account_report', 'crm_iap_', 'crm_lead_scoring_', 'gamification_',
    'spreadsheet_', 'link_tracker', 'theme_',
)
# the kinds of tables the report lists: the data, not the framework nor the relation tables
LISTED_KINDS = ('transaction', 'linked', 'kept')
CONFIRMATION_WORD = 'DELETE'
# how many times the tables the database refused to empty are tried again
MAX_PASSES = 8


class OmDataRemove(models.TransientModel):
    """ The Data Cleaning screen: what Clear All Transactions would delete, application by application """
    _name = 'om.data.remove'
    _description = 'Data Cleaning'

    summary = fields.Html(string='Transactions', compute='_compute_summary', sanitize=False)
    total_count = fields.Integer(string='Records', compute='_compute_summary')

    def _compute_display_name(self):
        for record in self:
            record.display_name = _('Data Cleaning')

    @api.model
    def _om_check_access(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Only the administrators can delete data.'))

    @api.model
    def _om_models(self):
        """ The transaction models installed on this database: (group key, group label, model) """
        found = []
        for key, label, names in TRANSACTION_GROUPS:
            for name in names:
                if name in self.env.registry:
                    model = self.env[name]
                    if not model._abstract and model._auto:
                        found.append((key, label, model))
        return found

    @api.model
    def _om_table_exists(self, table):
        self.env.cr.execute("SELECT to_regclass(%s) IS NOT NULL", [table])
        return self.env.cr.fetchone()[0]

    @api.model
    def _om_count(self, table):
        if not self._om_table_exists(table):
            return 0
        self.env.cr.execute(SQL('SELECT count(*) FROM %s', SQL.identifier(table)))
        return self.env.cr.fetchone()[0]

    @api.model
    def _om_counts(self):
        """ The number of rows of each installed transaction model, whatever the company or the state """
        return [(key, label, model, self._om_count(model._table)) for key, label, model in self._om_models()]

    def _compute_summary(self):
        counts = self._om_counts() if self.env.user.has_group('base.group_system') else []
        rows, total = [], 0
        groups = {}
        for key, label, model, count in counts:
            groups.setdefault((key, label), []).append((model, count))
        for (key, label), members in groups.items():
            group_total = sum(count for _model, count in members)
            total += group_total
            details = Markup(', ').join(
                Markup('%s <span class="text-muted">(%s)</span>') % (model._description or model._name, count)
                for model, count in members)
            rows.append(Markup(
                '<tr><td class="fw-bold text-nowrap">%s</td><td class="small">%s</td>'
                '<td class="text-end text-nowrap">%s</td></tr>') % (label, details, '{:,}'.format(group_total)))
        table = Markup(
            '<table class="table table-sm o_om_remove_summary"><thead><tr><th>Application</th>'
            '<th>Documents</th><th class="text-end">Records</th></tr></thead><tbody>%s</tbody>'
            '<tfoot><tr><th colspan="2">Total</th><th class="text-end">%s</th></tr></tfoot></table>'
        ) % (Markup('').join(rows), '{:,}'.format(total))
        for record in self:
            record.summary = table
            record.total_count = total

    def action_open_clear(self):
        """ Ask for the confirmation of Clear All Transactions """
        self._om_check_access()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Clear All Transactions'),
            'res_model': 'om.data.remove.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def action_table_report(self):
        """ The rows left in each table of the database, without deleting anything """
        self._om_check_access()
        return self.env['om.data.remove.report']._om_create_report(False)._om_open()

    # ------------------------------------------------------------------
    # Clearing
    # ------------------------------------------------------------------
    @api.model
    def _om_delete(self, table, where=None):
        """ Empty `table`, or the rows matching `where`, in a savepoint: a refusal of the database
        leaves the transaction usable. The number of rows deleted, or the error. """
        query = SQL('DELETE FROM %s', SQL.identifier(table))
        if where:
            query = SQL('%s WHERE %s', query, where)
        try:
            with self.env.cr.savepoint(flush=False):
                self.env.cr.execute(query, log_exceptions=False)
                return self.env.cr.rowcount, None
        except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
            # another transaction (a scheduled action, a user) changed these rows meanwhile: that is no
            # refusal of the database, so let Odoo run the whole request again rather than report it
            raise
        except psycopg2.Error as e:
            return 0, (e.pgerror or str(e)).strip()

    @api.model
    def _om_reset_sequences(self):
        """ Start the numbering of the cleared documents again from 1 """
        Sequence = self.env['ir.sequence'].sudo()
        sequences = Sequence.search([('code', 'in', SEQUENCE_CODES)])
        if 'stock.picking.type' in self.env:
            types = self.env['stock.picking.type'].sudo().with_context(active_test=False).search([])
            sequences |= types.sequence_id
        if sequences:
            sequences.write({'number_next': 1})
            sequences.date_range_ids.write({'number_next': 1})
        return len(sequences)

    @api.model
    def _om_delete_tables(self, targets):
        """ Empty the tables of `targets`, a list of (model name or False, table), then the records attached to
        those models. A table the database refuses to empty is tried again once the others are gone, until no
        more progress is made. Everything happens in the current transaction.

        :return: {'deleted': {table: rows}, 'errors': {table: reason}}
        """
        self._om_check_access()
        self.env.flush_all()
        deleted = {table: 0 for _name, table in targets}
        pending = list(targets)
        errors = {}
        for _pass in range(MAX_PASSES):
            blocked = []
            for name, table in pending:
                count, error = self._om_delete(table)
                if error:
                    blocked.append((name, table))
                    errors[table] = error
                else:
                    deleted[table] += count
                    errors.pop(table, None)
            stalled = len(blocked) == len(pending)
            pending = blocked
            if not pending or stalled:
                break
        names = [name for name, table in targets if name and table not in errors]
        for table, column in LINKED_TABLES:
            if names and self._om_table_exists(table):
                count, error = self._om_delete(table, SQL('%s IN %s', SQL.identifier(column), tuple(names)))
                deleted[table] = deleted.get(table, 0) + count
                if error:
                    errors[table] = error
        self.env.invalidate_all()
        # the XML ids of the deleted records are gone: forget the lookups cached for them
        self.env.transaction.invalidate_ormcache()
        return {'deleted': deleted, 'errors': errors}

    @api.model
    def _om_clear_all(self):
        """ Delete the transactions of every installed application, every message and activity, and what is
        attached to the deleted documents, then start their numbering again.

        :return: the result, for the report: deleted rows per table, the tables that could not be emptied
        """
        self._om_check_access()
        targets = [(model._name, model._table) for _key, _label, model in self._om_models()]
        result = self._om_delete_tables(targets)
        result['sequences'] = self._om_reset_sequences()
        result['action'] = 'clear'
        _logger.info('Data Cleaning by %s: %s rows deleted, %s tables could not be emptied',
                     self.env.user.login, sum(result['deleted'].values()), len(result['errors']))
        return result

    @api.model
    def _om_is_protected(self, table):
        return table in PROTECTED_TABLES or table.startswith(PROTECTED_PREFIXES)

    @api.model
    def _om_is_framework(self, table):
        return table in FRAMEWORK_TABLES or table.startswith(FRAMEWORK_PREFIXES)


class OmDataRemoveWizard(models.TransientModel):
    """ The confirmation of Clear All Transactions: nothing is deleted until the confirmation word is typed """
    _name = 'om.data.remove.wizard'
    _description = 'Clear All Transactions'

    record_count = fields.Integer(string='Records', compute='_compute_record_count')
    model_names = fields.Text(string='Documents', compute='_compute_record_count')
    confirmation = fields.Char(
        string='Confirmation', help='Type %s to confirm that the transactions are deleted for good.' % CONFIRMATION_WORD)

    def _compute_record_count(self):
        counts = self.env['om.data.remove']._om_counts()
        total = sum(count for _key, _label, _model, count in counts)
        names = ', '.join(model._description or model._name for _key, _label, model, count in counts if count)
        for wizard in self:
            wizard.record_count = total
            wizard.model_names = names

    def action_remove(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Only the administrators can delete data.'))
        if (self.confirmation or '').strip().upper() != CONFIRMATION_WORD:
            raise UserError(_('Type %s to confirm the removal.', CONFIRMATION_WORD))
        result = self.env['om.data.remove']._om_clear_all()
        return self.env['om.data.remove.report']._om_create_report(result)._om_open()


class OmDataRemoveReport(models.TransientModel):
    """ The tables of the database with the rows left in each, the most first, and the outcome of the
    clearing when there was one """
    _name = 'om.data.remove.report'
    _description = 'Database Tables'
    _order = 'id desc'

    cleared = fields.Boolean(string='After a Deletion', readonly=True)
    action = fields.Selection([('clear', 'Clear All Transactions'), ('tables', 'Delete Rows')], readonly=True)
    deleted_count = fields.Integer(string='Rows Deleted', readonly=True)
    blocked_count = fields.Integer(string='Tables Not Emptied', readonly=True)
    sequence_count = fields.Integer(string='Sequences Reset', readonly=True)
    outcome = fields.Html(string='Outcome', readonly=True, sanitize=False)
    table_count = fields.Integer(string='Tables', readonly=True)
    hidden_count = fields.Integer(string='Framework and Relation Tables', readonly=True,
                                  help="Not listed: the tables of the framework, of the configuration and the relation "
                                       "tables. Search the Tables shows them with the Framework filter.")
    nonempty_count = fields.Integer(string='Tables with Rows', readonly=True)
    row_count = fields.Integer(string='Rows Left', readonly=True)
    transaction_row_count = fields.Integer(string='Transaction Rows Left', readonly=True)
    line_ids = fields.One2many('om.data.remove.table', 'report_id', string='All Tables')
    nonempty_line_ids = fields.One2many('om.data.remove.table', 'report_id', string='Tables with Rows',
                                        domain=[('row_count', '>', 0), ('kind', 'in', LISTED_KINDS)])

    def _compute_display_name(self):
        for report in self:
            report.display_name = _('Database Tables')

    @api.model
    def _om_table_counts(self):
        """ The exact number of rows of every table of the database, in one query """
        self.env.cr.execute("""
            SELECT t.table_name,
                   (xpath('/row/n/text()', query_to_xml(format('SELECT count(*) AS n FROM %I.%I', t.table_schema,
                                                                t.table_name), false, true, '')))[1]::text::bigint
              FROM information_schema.tables t
             WHERE t.table_schema = current_schema() AND t.table_type = 'BASE TABLE'
        """)
        return self.env.cr.fetchall()

    @api.model
    def _om_create_report(self, result):
        self.env['om.data.remove']._om_check_access()
        cleaning = self.env['om.data.remove']
        transaction_models = {model._table: model for _key, _label, model in cleaning._om_models()}
        linked = {table for table, _column in LINKED_TABLES}
        model_of_table = {}
        for name in self.env.registry:
            model = self.env[name]
            if not model._abstract and model._auto:
                # several models may share a table: the regular one names it
                if model._table not in model_of_table or model_of_table[model._table]._transient:
                    model_of_table[model._table] = model
        lines = []
        for table, rows in self._om_table_counts():
            model = transaction_models.get(table) or model_of_table.get(table)
            if table in transaction_models:
                kind = 'transaction'
            elif cleaning._om_is_framework(table) or (model is not None and model._transient):
                kind = 'framework'
            elif table in linked:
                kind = 'linked'
            elif model is not None and not model._transient:
                kind = 'kept'
            else:
                kind = 'technical'
            lines.append({
                'table_name': table,
                'model': model._name if model is not None else False,
                'model_label': (model._description or model._name) if model is not None else False,
                'row_count': rows or 0,
                'kind': kind,
                'deleted_count': (result or {}).get('deleted', {}).get(table, 0),
                'can_delete': kind in ('transaction', 'linked', 'kept') and model is not None
                              and not cleaning._om_is_protected(table),
                'error': (result or {}).get('errors', {}).get(table),
            })
        # the list and its figures are about the data: the framework and the relation tables are left out
        listed = [line for line in lines if line['kind'] in LISTED_KINDS]
        values = {
            'table_count': len(listed),
            'hidden_count': len(lines) - len(listed),
            'nonempty_count': sum(1 for line in listed if line['row_count']),
            'row_count': sum(line['row_count'] for line in listed),
            'transaction_row_count': sum(line['row_count'] for line in lines if line['kind'] == 'transaction'),
            'line_ids': [fields.Command.create(line) for line in lines],
        }
        if result:
            errors = result['errors']
            items = Markup('').join(Markup('<li><code>%s</code>: %s</li>') % (table, error.splitlines()[0])
                                    for table, error in sorted(errors.items()))
            values.update(
                cleared=True,
                action=result.get('action', 'clear'),
                deleted_count=sum(result['deleted'].values()),
                blocked_count=len(errors),
                sequence_count=result.get('sequences', 0),
                outcome=Markup('<ul class="mb-0">%s</ul>') % items if errors else False,
            )
        return self.create(values)

    def _om_open(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Database Tables'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def action_view_tables(self):
        """ Every table of the report, in a list that can be searched, filtered and grouped """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Database Tables'),
            'res_model': 'om.data.remove.table',
            'view_mode': 'list',
            'views': [(False, 'list')],
            'domain': [('report_id', '=', self.id)],
            'context': {'search_default_with_rows': 1, 'search_default_data': 1},
            'target': 'current',
        }


class OmDataRemoveTable(models.TransientModel):
    """ A table of the database and the rows it holds """
    _name = 'om.data.remove.table'
    _description = 'Database Table'
    _order = 'row_count desc, table_name'
    _rec_name = 'table_name'

    report_id = fields.Many2one('om.data.remove.report', required=True, ondelete='cascade', index=True)
    table_name = fields.Char(string='Table', required=True)
    model = fields.Char(string='Model')
    model_label = fields.Char(string='Description')
    row_count = fields.Integer(string='Rows')
    deleted_count = fields.Integer(string='Deleted')
    kind = fields.Selection([
        ('transaction', 'Transactions'),
        ('linked', 'Attached to documents'),
        ('kept', 'Kept records'),
        ('technical', 'Relation or technical'),
        ('framework', 'Framework and configuration'),
    ], string='Kind')
    error = fields.Char(string='Why It Was Not Emptied')
    can_delete = fields.Boolean(string='Can Be Emptied', help="The framework tables are never offered for deletion.")

    def action_delete_rows(self):
        """ Ask for the confirmation of emptying the selected tables """
        self.env['om.data.remove']._om_check_access()
        lines = self.filtered('can_delete')
        if not lines:
            raise UserError(_('None of these tables can be emptied here: the tables of the framework are protected, '
                              'and a relation table is emptied with the records it links.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Delete Rows'),
            'res_model': 'om.data.remove.table.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_line_ids': lines.ids},
        }


class OmDataRemoveTableWizard(models.TransientModel):
    """ The confirmation of emptying some tables, chosen in the report of the database tables """
    _name = 'om.data.remove.table.wizard'
    _description = 'Delete Rows'

    line_ids = fields.Many2many('om.data.remove.table', string='Tables')
    record_count = fields.Integer(string='Records', compute='_compute_record_count')
    table_names = fields.Text(string='Tables to Empty', compute='_compute_record_count')
    confirmation = fields.Char(
        string='Confirmation', help='Type %s to confirm that the rows are deleted for good.' % CONFIRMATION_WORD)

    @api.depends('line_ids')
    def _compute_record_count(self):
        cleaning = self.env['om.data.remove']
        for wizard in self:
            lines = wizard.line_ids.filtered('can_delete')
            wizard.record_count = sum(cleaning._om_count(line.table_name) for line in lines)
            wizard.table_names = ', '.join('%s (%s)' % (line.table_name, line.model_label or line.model or '')
                                           for line in lines)

    def action_remove(self):
        self.ensure_one()
        cleaning = self.env['om.data.remove']
        cleaning._om_check_access()
        if (self.confirmation or '').strip().upper() != CONFIRMATION_WORD:
            raise UserError(_('Type %s to confirm the removal.', CONFIRMATION_WORD))
        lines = self.line_ids.filtered(lambda line: line.can_delete and not cleaning._om_is_protected(line.table_name))
        if not lines:
            raise UserError(_('There is no table to empty.'))
        result = cleaning._om_delete_tables([(line.model or False, line.table_name) for line in lines])
        result['action'] = 'tables'
        _logger.info('Data Cleaning by %s emptied %s: %s rows deleted', self.env.user.login,
                     ', '.join(lines.mapped('table_name')), sum(result['deleted'].values()))
        return self.env['om.data.remove.report']._om_create_report(result)._om_open()
