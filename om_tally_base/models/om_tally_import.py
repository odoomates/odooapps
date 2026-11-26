import hashlib
import io
import logging
import re
from collections import Counter, defaultdict
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain
from odoo.tools import SQL
from odoo.tools.misc import file_open

from ..tools import (
    ACCOUNTING_VOUCHER_TYPES, TallyClient, TallyConnectionError, TallyXmlError, iter_tally_objects, read_tally_objects,
    tally_due_date,
)

_logger = logging.getLogger(__name__)

# tag of Tally XML -> staging model
MASTER_MODELS = {
    'GROUP': 'om.tally.group',
    'LEDGER': 'om.tally.ledger',
    'VOUCHERTYPE': 'om.tally.voucher.type',
    'COSTCATEGORY': 'om.tally.cost.category',
    'COSTCENTRE': 'om.tally.cost.centre',
    'CURRENCY': 'om.tally.currency',
    'UNIT': 'om.tally.unit',
    'STOCKGROUP': 'om.tally.stock.group',
    'STOCKCATEGORY': 'om.tally.stock.category',
    'GODOWN': 'om.tally.godown',
    'STOCKITEM': 'om.tally.stock.item',
}
BILL_TYPES = {'new ref': 'new', 'agst ref': 'agst', 'advance': 'advance', 'on account': 'on_account'}
COMPANY_FIELDS = {
    'guid': 'tally_company_guid', 'books_from': 'books_from', 'starting_from': 'starting_from',
    'currency_symbol': 'tally_currency_symbol', 'gstin': 'tally_gstin', 'state_name': 'tally_state_name',
    'country_name': 'tally_country_name', 'pincode': 'tally_pincode', 'email': 'tally_email', 'phone': 'tally_phone',
    'address': 'tally_address', 'pan': 'tally_pan', 'mailing_name': 'tally_mailing_name',
}
COUNTRIES = {
    'india': 'in', 'united arab emirates': 'ae', 'uae': 'ae', 'saudi arabia': 'sa', 'kingdom of saudi arabia': 'sa',
    'ksa': 'sa', 'bahrain': 'bh', 'kingdom of bahrain': 'bh',
}
GSTIN = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$')
TRN = re.compile(r'^[0-9]{15}$')
# records staged at once when reading in the background
READ_CHUNK = 500


class OmTallyImport(models.Model):
    """ One Tally company brought into one Odoo company: where the data comes from, what was read, and every
    step of the import. """
    _name = 'om.tally.import'
    _description = 'Tally Import'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(required=True, default=lambda self: self.env._("New Tally Import"), tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Odoo Company', required=True,
                                 default=lambda self: self.env.company, tracking=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    state = fields.Selection([
        ('draft', 'Connect'),
        ('analyzed', 'Analyze'),
    ], default='draft', required=True, tracking=True, copy=False)

    # source
    source_type = fields.Selection([
        ('file', 'XML Files Exported from Tally'),
        ('direct', 'Direct Connection to Tally'),
    ], string='Source', default='file', required=True, tracking=True)
    file_ids = fields.Many2many('ir.attachment', string='Tally Files',
                                help="The XML files exported from Tally: masters (Display More Reports > "
                                     "List of Accounts > Export, all masters) and vouchers (Day Book > Export), "
                                     "in XML format.")
    host = fields.Char(string='Tally Host', default='localhost',
                       help="The name or address of the computer that runs Tally.")
    port = fields.Integer(string='Tally Port', default=9000)
    timeout = fields.Integer(string='Timeout (seconds)', default=120)
    read_file_ids = fields.Many2many('ir.attachment', 'om_tally_import_read_file_rel', 'import_id', 'attachment_id',
                                     string='Files Read', readonly=True, copy=False)
    remote_company_ids = fields.One2many('om.tally.remote.company', 'import_id', string='Companies in Tally')

    # company of Tally
    tally_company_name = fields.Char(string='Tally Company', tracking=True)
    tally_company_guid = fields.Char(string='Tally Company GUID', readonly=True)
    tally_mailing_name = fields.Char(string='Mailing Name', readonly=True)
    books_from = fields.Date(string='Books Beginning From', tracking=True,
                             help="The date of the opening balances in Tally.")
    starting_from = fields.Date(string='Financial Year From', help="The first day of the financial year in Tally.")
    tally_currency_symbol = fields.Char(string='Base Currency Symbol', readonly=True)
    tally_gstin = fields.Char(string='Company GSTIN/TRN', readonly=True)
    tally_pan = fields.Char(string='Company PAN', readonly=True)
    tally_state_name = fields.Char(string='Company State', readonly=True)
    tally_country_name = fields.Char(string='Company Country', readonly=True)
    tally_pincode = fields.Char(string='Company PIN Code', readonly=True)
    tally_email = fields.Char(string='Company Email', readonly=True)
    tally_phone = fields.Char(string='Company Phone', readonly=True)
    tally_address = fields.Text(string='Company Address', readonly=True)
    tally_country = fields.Selection([
        ('in', 'India'),
        ('ae', 'United Arab Emirates'),
        ('sa', 'Saudi Arabia'),
        ('bh', 'Bahrain'),
        ('other', 'Other'),
    ], string='Tally Country', compute='_compute_tally_country', store=True, readonly=False, tracking=True,
        help="The country of the Tally company. It sets the tax number read on the parties (GSTIN in India, TRN in "
             "the Gulf), the taxes the tax ledgers are matched with, and the fiscal year of a new Odoo company. "
             "Filled from Tally: check it.")
    tax_number_label = fields.Char(compute='_compute_tax_number_label')

    # vouchers to read from Tally
    voucher_date_from = fields.Date(string='Read Vouchers From',
                                    help="Empty: from the books beginning date.")
    voucher_date_to = fields.Date(string='Read Vouchers Until', help="Empty: until today.")
    period_ids = fields.One2many('om.tally.period', 'import_id', string='Periods')
    sync_enabled = fields.Boolean(string='Keep in Sync',
                                  help="Read the vouchers created or changed in Tally every hour (direct connection) "
                                       "and import them.")
    # reading in the background
    read_background = fields.Boolean(string='Read in the Background',
                                     help="Read Tally in a background job, one file or one month at a time: for big "
                                          "companies. You can close the browser meanwhile.")
    read_state = fields.Selection([
        ('idle', 'Not Started'),
        ('queued', 'Waiting'),
        ('running', 'Reading'),
        ('done', 'Done'),
        ('error', 'Error'),
    ], string='Background Reading', default='idle', required=True, readonly=True, copy=False)
    read_queue = fields.Json(readonly=True, copy=False)
    read_offset = fields.Integer(readonly=True, copy=False,
                                 help="The records of the current file already read: the job resumes after them.")
    read_total = fields.Integer(readonly=True, copy=False)
    read_step_ratio = fields.Float(readonly=True, copy=False, help="How far the current step is, from 0 to 1.")
    read_progress = fields.Float(string='Reading Progress', compute='_compute_read_progress')
    read_message = fields.Char(string='Reading Status', readonly=True, copy=False)
    last_alter_id = fields.Integer(string='Last Alter ID', readonly=True, copy=False,
                                   help="The highest Alter ID read from Tally: the next sync reads what came after.")
    last_read = fields.Datetime(string='Last Read', readonly=True, copy=False)

    # staging
    group_ids = fields.One2many('om.tally.group', 'import_id', string='Groups')
    ledger_ids = fields.One2many('om.tally.ledger', 'import_id', string='Ledgers')
    voucher_ids = fields.One2many('om.tally.voucher', 'import_id', string='Vouchers')
    problem_ids = fields.One2many('om.tally.problem', 'import_id', string='Problems')
    log_ids = fields.One2many('om.tally.log', 'import_id', string='Log')
    mapping_ids = fields.One2many('om.tally.mapping', 'import_id', string='Mappings')
    group_count = fields.Integer(compute='_compute_counts')
    ledger_count = fields.Integer(compute='_compute_counts')
    party_count = fields.Integer(string='Parties', compute='_compute_counts')
    voucher_count = fields.Integer(compute='_compute_counts')
    voucher_type_count = fields.Integer(compute='_compute_counts')
    cost_centre_count = fields.Integer(compute='_compute_counts')
    stock_item_count = fields.Integer(compute='_compute_counts')
    godown_count = fields.Integer(compute='_compute_counts')
    unit_count = fields.Integer(compute='_compute_counts')
    currency_count = fields.Integer(compute='_compute_counts')
    problem_count = fields.Integer(compute='_compute_counts')
    mapping_count = fields.Integer(compute='_compute_counts')
    opening_difference = fields.Monetary(string='Difference in Opening Balances', compute='_compute_opening',
                                         help="Debit minus credit of the opening balances of Tally. Tally shows it "
                                              "as 'Difference in opening balances'.")
    opening_debit_total = fields.Monetary(string='Total Opening Debit', compute='_compute_opening')
    opening_credit_total = fields.Monetary(string='Total Opening Credit', compute='_compute_opening')
    analysis_html = fields.Html(string='Analysis', compute='_compute_analysis_html', sanitize=False)

    # ------------------------------------------------------------------------------------------------------------
    # computes

    @api.depends('tally_country_name', 'tally_gstin', 'company_id')
    def _compute_tally_country(self):
        for record in self:
            code = COUNTRIES.get((record.tally_country_name or '').strip().lower())
            number = (record.tally_gstin or '').strip().upper()
            if not code and number:
                if GSTIN.match(number):
                    code = 'in'
                elif TRN.match(number):
                    code = 'ae' if number.startswith('100') else 'sa' if number.startswith('3') else False
            if not code and not record.tally_country:
                company_code = (record.company_id.country_id.code or '').lower()
                code = company_code if company_code in ('in', 'ae', 'sa', 'bh') else 'other'
            record.tally_country = code or record.tally_country or 'other'

    @api.depends('tally_country')
    def _compute_tax_number_label(self):
        for record in self:
            record.tax_number_label = {'in': 'GSTIN', 'ae': 'TRN', 'sa': 'VAT Number', 'bh': 'VAT Number'}.get(
                record.tally_country, self.env._("Tax Number"))

    @api.depends('read_total', 'read_queue', 'read_state', 'read_step_ratio')
    def _compute_read_progress(self):
        for record in self:
            if record.read_state == 'done':
                record.read_progress = 100.0
            elif record.read_total:
                done = record.read_total - len(record.read_queue or []) + (record.read_step_ratio or 0.0)
                record.read_progress = 100.0 * done / record.read_total
            else:
                record.read_progress = 0.0

    def _compute_counts(self):
        def count(model, extra=None):
            domain = Domain('import_id', 'in', self.ids) & Domain(extra or [])
            return dict(self.env[model]._read_group(domain, ['import_id'], ['__count']))
        groups, ledgers = count('om.tally.group'), count('om.tally.ledger')
        parties = count('om.tally.ledger', [('role', 'in', ('receivable', 'payable'))])
        vouchers, voucher_types = count('om.tally.voucher'), count('om.tally.voucher.type')
        cost_centres, items = count('om.tally.cost.centre'), count('om.tally.stock.item')
        godowns, units, currencies = count('om.tally.godown'), count('om.tally.unit'), count('om.tally.currency')
        problems = count('om.tally.problem', [('level', '!=', 'info')])
        mappings = dict(self.env['om.tally.mapping']._read_group(
            [('company_id', 'in', self.company_id.ids)], ['company_id'], ['__count']))
        for record in self:
            record.group_count = groups.get(record, 0)
            record.ledger_count = ledgers.get(record, 0)
            record.party_count = parties.get(record, 0)
            record.voucher_count = vouchers.get(record, 0)
            record.voucher_type_count = voucher_types.get(record, 0)
            record.cost_centre_count = cost_centres.get(record, 0)
            record.stock_item_count = items.get(record, 0)
            record.godown_count = godowns.get(record, 0)
            record.unit_count = units.get(record, 0)
            record.currency_count = currencies.get(record, 0)
            record.problem_count = problems.get(record, 0)
            record.mapping_count = mappings.get(record.company_id, 0)

    def _compute_opening(self):
        for record in self:
            balances = record.ledger_ids.mapped('opening_balance')
            debit = sum(balance for balance in balances if balance > 0)
            credit = -sum(balance for balance in balances if balance < 0)
            record.opening_debit_total = debit
            record.opening_credit_total = credit
            record.opening_difference = record.currency_id.round(debit - credit)

    @api.depends('voucher_ids', 'ledger_ids', 'problem_ids')
    def _compute_analysis_html(self):
        for record in self:
            record.analysis_html = record._om_tally_analysis_html() if record.id else False

    # ------------------------------------------------------------------------------------------------------------
    # helpers

    def _om_tally_log(self, message, level='info', step=None):
        self.ensure_one()
        self.env['om.tally.log'].sudo().create({
            'import_id': self.id, 'message': message, 'level': level, 'step': step,
        })
        if level == 'error':
            _logger.warning("Tally import %s: %s", self.id, message)

    def _om_tally_client(self):
        self.ensure_one()
        if not self.host:
            raise UserError(self.env._("Enter the host of the computer that runs Tally."))
        return TallyClient(self.host, self.port or 9000, self.timeout or 120)

    def _om_tally_period(self):
        """ (first day, last day) of the vouchers to read. """
        self.ensure_one()
        date_from = self.voucher_date_from or self.books_from or self.starting_from
        if not date_from:
            raise UserError(self.env._("Enter the books beginning date of the Tally company, or the date from which "
                                       "to read the vouchers."))
        return date_from, self.voucher_date_to or fields.Date.context_today(self)

    # ------------------------------------------------------------------------------------------------------------
    # staging

    def _om_tally_stage(self, objects):
        """ Write what Tally sent into the staging tables, in place of the same records read before (same GUID, or
        same name for masters without one). Returns the vouchers created or changed. """
        self.ensure_one()
        if objects.get('current_company') and not self.tally_company_name:
            self.tally_company_name = objects['current_company']
        companies = objects.get('COMPANY') or []
        if companies:
            company = next((values for values in companies if values['name'] == self.tally_company_name),
                           companies[0])
            self._om_tally_stage_company(company)
        counts = Counter()
        for tag, model in MASTER_MODELS.items():
            records = objects.get(tag) or []
            if records:
                counts[tag] = self._om_tally_stage_masters(model, records)
        vouchers = self.env['om.tally.voucher']
        if objects.get('VOUCHER'):
            vouchers = self._om_tally_stage_vouchers(objects['VOUCHER'])
            counts['VOUCHER'] = len(objects['VOUCHER'])
        alter_ids = [values.get('alter_id') or 0 for tag in list(MASTER_MODELS) + ['VOUCHER']
                     for values in objects.get(tag) or []]
        if alter_ids and max(alter_ids) > self.last_alter_id:
            self.last_alter_id = max(alter_ids)
        self.last_read = fields.Datetime.now()
        if counts:
            self._om_tally_log(self.env._("Read: %s", ", ".join(f"{tag.lower()} {count}" for tag, count in
                                                                 sorted(counts.items()))), step='read')
        return vouchers

    def _om_tally_stage_company(self, values):
        updates = {target: values[source] for source, target in COMPANY_FIELDS.items() if values.get(source)}
        if values.get('name') and not self.tally_company_name:
            updates['tally_company_name'] = values['name']
        self.write(updates)

    def _om_tally_stage_masters(self, model, records):
        Model = self.env[model].with_context(active_test=False)
        existing = Model.search([('import_id', '=', self.id)])
        by_guid = {record.guid: record for record in existing if record.guid}
        by_name = {record.name: record for record in existing}
        allowed = set(Model._fields) - {'id', 'import_id', 'company_id'}
        to_create = []
        for values in records:
            record = by_guid.get(values.get('guid')) or by_name.get(values['name'])
            if values.get('action') == 'delete':
                if record:
                    record.unlink()
                continue
            vals = {key: value for key, value in values.items() if key in allowed}
            if model == 'om.tally.ledger':
                vals['bill_ids'] = [Command.clear()] + [Command.create(bill) for bill in values.get('bills', [])]
            if model == 'om.tally.stock.item':
                vals['opening_ids'] = [Command.clear()] + [
                    Command.create({key: value for key, value in opening.items()})
                    for opening in values.get('openings', [])]
            if record:
                if values.get('alter_id') and record.alter_id and values['alter_id'] < record.alter_id:
                    continue
                record.write(vals)
            else:
                vals['import_id'] = self.id
                to_create.append(vals)
                by_name[values['name']] = True
        if to_create:
            Model.create(to_create)
        return len(records)

    def _om_tally_voucher_vals(self, values):
        lines = []
        for sequence, line in enumerate(values['lines'], start=1):
            bills = [Command.create({
                'name': bill['name'],
                'bill_type': BILL_TYPES.get(bill['bill_type'].lower(), 'on_account'),
                'amount': bill['amount'],
                'credit_period': bill['credit_period'],
                'due_date': tally_due_date(values['date'], bill['credit_period']),
            }) for bill in line['bills']]
            costs = [Command.create({'category_name': cost['category_name'], 'name': cost['name'],
                                     'amount': cost['amount']}) for cost in line['costs']]
            lines.append(Command.create({
                'sequence': sequence,
                'ledger_name': line['ledger_name'],
                'amount': line['amount'],
                'is_deemed_positive': line['is_deemed_positive'],
                'is_party': line['is_party'] or line['ledger_name'] == values['party_name'],
                'from_inventory': line['from_inventory'],
                'instrument_number': line['instrument_number'],
                'instrument_date': line['instrument_date'],
                'bill_ids': bills,
                'cost_ids': costs,
            }))
        inventory = [Command.create(line) for line in values['inventory']]
        vals = {key: values[key] for key in (
            'guid', 'alter_id', 'master_id', 'date', 'effective_date', 'voucher_type_name', 'number', 'reference',
            'reference_date', 'party_name', 'narration', 'is_cancelled', 'is_optional', 'is_postdated', 'is_invoice',
            'is_deleted', 'view')}
        vals.update({'line_ids': [Command.clear()] + lines, 'inventory_ids': [Command.clear()] + inventory})
        return vals

    def _om_tally_stage_vouchers(self, records):
        Voucher = self.env['om.tally.voucher']
        guids = [values['guid'] for values in records if values.get('guid')]
        existing = Voucher.search([('import_id', '=', self.id), ('guid', 'in', guids)]) if guids else Voucher
        by_guid = {voucher.guid: voucher for voucher in existing}
        to_create, changed = [], Voucher
        for values in records:
            if not values.get('date'):
                continue
            if not values.get('guid'):
                values['guid'] = 'nokey:' + hashlib.sha1(
                    f"{values['voucher_type_name']}|{values['number']}|{values['date']}|{values['party_name']}".encode()
                ).hexdigest()
            voucher = by_guid.get(values['guid'])
            if voucher:
                if values.get('alter_id') and voucher.alter_id and values['alter_id'] <= voucher.alter_id \
                        and not values['is_deleted']:
                    continue
                vals = self._om_tally_voucher_vals(values)
                if voucher.state == 'posted':
                    vals['is_changed'] = True
                elif voucher.state in ('skipped', 'error'):
                    vals['state'] = 'staged'
                voucher.write(vals)
                changed |= voucher
            elif not values['is_deleted']:
                vals = self._om_tally_voucher_vals(values)
                vals['import_id'] = self.id
                to_create.append(vals)
                by_guid[values['guid']] = True
        created = Voucher.create(to_create) if to_create else Voucher
        return created | changed

    def _om_tally_link(self):
        """ Link the staging records to each other: Tally refers to records by name. """
        self.ensure_one()
        env = self.env

        def names(model):
            return {record.name: record for record in env[model].search([('import_id', '=', self.id)])}

        groups = names('om.tally.group')
        for group in groups.values():
            parent = groups.get(group.parent_name)
            if group.parent_id != (parent or env['om.tally.group']) and parent != group:
                group.parent_id = parent
        ledgers = names('om.tally.ledger')
        for ledger in ledgers.values():
            group = groups.get(ledger.parent_name) or env['om.tally.group']
            if ledger.group_id != group:
                ledger.group_id = group
        voucher_types = names('om.tally.voucher.type')
        for voucher_type in voucher_types.values():
            parent = voucher_types.get(voucher_type.parent_name)
            if parent and parent != voucher_type and voucher_type.parent_id != parent:
                voucher_type.parent_id = parent
        categories = names('om.tally.cost.category')
        centres = names('om.tally.cost.centre')
        for centre in centres.values():
            centre.write({'parent_id': centres.get(centre.parent_name, env['om.tally.cost.centre']).id,
                          'category_id': categories.get(centre.category_name, env['om.tally.cost.category']).id})
        for model, parent_model in (('om.tally.stock.group', None), ('om.tally.stock.category', None),
                                    ('om.tally.godown', None)):
            records = names(model)
            for record in records.values():
                parent = records.get(record.parent_name)
                if parent and parent != record and record.parent_id != parent:
                    record.parent_id = parent
        stock_groups, stock_categories = names('om.tally.stock.group'), names('om.tally.stock.category')
        units, godowns = names('om.tally.unit'), names('om.tally.godown')
        items = names('om.tally.stock.item')
        for item in items.values():
            item.write({
                'stock_group_id': stock_groups.get(item.parent_name, env['om.tally.stock.group']).id,
                'stock_category_id': stock_categories.get(item.category_name, env['om.tally.stock.category']).id,
                'unit_id': units.get(item.base_unit_name, env['om.tally.unit']).id,
            })
            for opening in item.opening_ids:
                opening.godown_id = godowns.get(opening.godown_name, env['om.tally.godown'])
        # vouchers: grouped writes keep the stored computes right
        vouchers = env['om.tally.voucher'].search([('import_id', '=', self.id)])
        for type_name, type_vouchers in vouchers.grouped('voucher_type_name').items():
            voucher_type = voucher_types.get(type_name, env['om.tally.voucher.type'])
            type_vouchers.filtered(lambda v: v.voucher_type_id != voucher_type).voucher_type_id = voucher_type
        for party_name, party_vouchers in vouchers.grouped('party_name').items():
            party = ledgers.get(party_name, env['om.tally.ledger'])
            party_vouchers.filtered(lambda v: v.party_ledger_id != party).party_ledger_id = party
        # lines: plain SQL, nothing stored depends on these links
        env['om.tally.voucher.line'].flush_model()
        env['om.tally.voucher.cost'].flush_model()
        env['om.tally.voucher.inventory'].flush_model()
        env.cr.execute(SQL("""
            UPDATE om_tally_voucher_line line SET ledger_id = ledger.id
              FROM om_tally_ledger ledger
             WHERE line.import_id = %(import_id)s AND ledger.import_id = %(import_id)s
               AND ledger.name = line.ledger_name AND line.ledger_id IS DISTINCT FROM ledger.id
        """, import_id=self.id))
        env.cr.execute(SQL("""
            UPDATE om_tally_voucher_cost cost SET cost_centre_id = centre.id
              FROM om_tally_cost_centre centre
             WHERE cost.import_id = %(import_id)s AND centre.import_id = %(import_id)s
               AND centre.name = cost.name AND cost.cost_centre_id IS DISTINCT FROM centre.id
        """, import_id=self.id))
        env.cr.execute(SQL("""
            UPDATE om_tally_voucher_inventory line SET item_id = item.id
              FROM om_tally_stock_item item
             WHERE line.import_id = %(import_id)s AND item.import_id = %(import_id)s
               AND item.name = line.item_name AND line.item_id IS DISTINCT FROM item.id
        """, import_id=self.id))
        env.cr.execute(SQL("""
            UPDATE om_tally_voucher_inventory line SET godown_id = godown.id
              FROM om_tally_godown godown
             WHERE line.import_id = %(import_id)s AND godown.import_id = %(import_id)s
               AND godown.name = line.godown_name AND line.godown_id IS DISTINCT FROM godown.id
        """, import_id=self.id))
        env['om.tally.voucher.line'].invalidate_model(['ledger_id'])
        env['om.tally.voucher.cost'].invalidate_model(['cost_centre_id'])
        env['om.tally.voucher.inventory'].invalidate_model(['item_id', 'godown_id'])
        if not self.books_from:
            first = env['om.tally.voucher'].search([('import_id', '=', self.id)], order='date', limit=1)
            if first:
                month = self.starting_from.month if self.starting_from else 4
                year = first.date.year if first.date.month >= month else first.date.year - 1
                self.books_from = date(year, month, 1)
        if not self.starting_from and self.books_from:
            self.starting_from = self.books_from

    # ------------------------------------------------------------------------------------------------------------
    # reading the sources

    def _om_tally_attachment_stream(self, attachment):
        """ A binary stream of an attachment, read piece by piece from the file store. """
        raw = attachment.raw
        if hasattr(raw, 'open'):
            return raw.open()
        return io.BytesIO(bytes(raw or b''))

    def _om_tally_files_to_read(self, only_new=True):
        self.ensure_one()
        if not self.file_ids:
            raise UserError(self.env._("Add the XML files exported from Tally first."))
        files = (self.file_ids - self.read_file_ids) if only_new else self.file_ids
        if not files and only_new:
            raise UserError(self.env._("Every file was read already: add the export of the next period, or use "
                                       "Read Again to read all the files again."))
        return files

    def _om_tally_read_files(self, only_new=True):
        self.ensure_one()
        for attachment in self._om_tally_files_to_read(only_new):
            try:
                with self._om_tally_attachment_stream(attachment) as stream:
                    objects = read_tally_objects(stream)
            except TallyXmlError as error:
                self._om_tally_log(self.env._("%(file)s cannot be read: %(error)s", file=attachment.name,
                                              error=error), level='error', step='read')
                continue
            if objects['errors']:
                self._om_tally_log(self.env._("%(file)s: Tally reports %(errors)s", file=attachment.name,
                                              errors="; ".join(objects['errors'][:5])), level='warning', step='read')
            self._om_tally_stage(objects)
            self.read_file_ids = [Command.link(attachment.id)]

    def _om_tally_direct_company(self, client):
        if not self.tally_company_name:
            self.action_test_connection()
        if not self.tally_company_name:
            raise UserError(self.env._("Choose the company of Tally to read."))
        try:
            details = client.company_details(self.tally_company_name)
        except TallyConnectionError as error:
            details = []
            self._om_tally_log(self.env._("The details of the company were not read: %s", error), 'warning', 'read')
        if details:
            self._om_tally_stage_company(details[0])
        return self.tally_company_name

    def _om_tally_months(self):
        """ [(first day, last day)] of the months of vouchers to read. """
        date_from, date_to = self._om_tally_period()
        months, month = [], date_from.replace(day=1)
        while month <= date_to:
            months.append((max(month, date_from), min(month + relativedelta(months=1, days=-1), date_to)))
            month += relativedelta(months=1)
        return months

    def _om_tally_read_direct(self):
        self.ensure_one()
        client = self._om_tally_client()
        company = self._om_tally_direct_company(client)
        masters, _data = client.masters(company)
        self._om_tally_stage(masters)
        for date_from, date_to in self._om_tally_months():
            vouchers, _data = client.vouchers(company, date_from, date_to)
            self._om_tally_stage(vouchers)

    # reading in the background

    def _om_tally_start_background_read(self, only_new=True):
        """ Queue the steps of the reading: one file, or the masters then one month of vouchers, per step. """
        self.ensure_one()
        if self.source_type == 'file':
            queue = [{'kind': 'file', 'id': attachment.id, 'name': attachment.name}
                     for attachment in self._om_tally_files_to_read(only_new)]
        else:
            self._om_tally_direct_company(self._om_tally_client())
            queue = [{'kind': 'masters', 'name': self.env._("Masters")}] + [
                {'kind': 'month', 'from': str(date_from), 'to': str(date_to), 'name': date_from.strftime('%b %Y')}
                for date_from, date_to in self._om_tally_months()]
        self.write({'read_queue': queue, 'read_total': len(queue), 'read_offset': 0, 'read_state': 'queued',
                    'read_message': self.env._("Waiting for the background job.")})
        self._om_tally_log(self.env._("Reading in the background: %s steps.", len(queue)), step='read')
        self.env.ref('om_tally_base.ir_cron_om_tally_read')._trigger()

    def _om_tally_stage_chunk(self, chunk):
        objects = defaultdict(list)
        for tag, values in chunk:
            objects[tag].append(values)
        self._om_tally_stage(objects)

    def _om_tally_read_step(self, step):
        """ Read one step; False when the time of the job ran out (the step resumes from read_offset). """
        Cron = self.env['ir.cron']
        if step['kind'] == 'file':
            attachment = self.env['ir.attachment'].browse(step['id']).exists()
            if not attachment:
                return True
            skip, chunk, read = self.read_offset, [], 0
            with self._om_tally_attachment_stream(attachment) as stream:
                for tag, values in iter_tally_objects(stream):
                    if tag == 'current_company':
                        if not self.tally_company_name:
                            self.tally_company_name = values
                        continue
                    if tag == 'errors':
                        self._om_tally_log(self.env._("%(file)s: Tally reports %(errors)s", file=attachment.name,
                                                      errors="; ".join(values[:5])), 'warning', 'read')
                        continue
                    read += 1
                    if read <= skip:
                        continue
                    chunk.append((tag, values))
                    if len(chunk) >= READ_CHUNK:
                        self._om_tally_stage_chunk(chunk)
                        ratio = min(stream.tell() / attachment.file_size, 0.99) if attachment.file_size else 0.0
                        self.write({'read_offset': read, 'read_step_ratio': ratio, 'read_message': self.env._(
                            "%(file)s: %(count)s records read", file=attachment.name, count=read)})
                        chunk = []
                        if Cron._commit_progress(0) <= 0:
                            return False
            if chunk:
                self._om_tally_stage_chunk(chunk)
            self.read_file_ids = [Command.link(attachment.id)]
            return True
        client = self._om_tally_client()
        if step['kind'] == 'masters':
            objects, _data = client.masters(self.tally_company_name)
        else:
            objects, _data = client.vouchers(self.tally_company_name, fields.Date.to_date(step['from']),
                                             fields.Date.to_date(step['to']))
        self._om_tally_stage(objects)
        return True

    @api.model
    def _cron_om_tally_read(self):
        Cron = self.env['ir.cron']
        for record in self.search([('read_state', 'in', ('queued', 'running'))]):
            record.read_state = 'running'
            while record.read_queue:
                step = record.read_queue[0]
                try:
                    # each chunk is committed: an error undoes the current chunk only
                    finished = record._om_tally_read_step(step)
                except (TallyXmlError, TallyConnectionError, UserError) as error:
                    self.env.cr.rollback()
                    self.env.invalidate_all()
                    record.write({'read_state': 'error', 'read_message': str(error)})
                    record._om_tally_log(self.env._("Reading %(step)s failed: %(error)s", step=step.get('name'),
                                                    error=error), 'error', 'read')
                    Cron._commit_progress(0)
                    break
                if not finished:
                    return
                record.write({'read_queue': record.read_queue[1:], 'read_offset': 0, 'read_step_ratio': 0.0,
                              'read_message': self.env._(
                    "%s read.", step.get('name'))})
                if Cron._commit_progress(1, remaining=len(record.read_queue or [])) <= 0:
                    return
            if record.read_state == 'running' and not record.read_queue:
                record._om_tally_finish_read()
                record.write({'read_state': 'done', 'read_message': self.env._("Everything was read.")})
                Cron._commit_progress(0)

    def _om_tally_finish_read(self):
        if self.tally_company_name and self.name == self.env._("New Tally Import"):
            self.name = self.tally_company_name
        self.action_analyze()
        self._om_tally_after_read()

    def _om_tally_after_read(self):
        """ Hook: a reading of the source finished. """
        return True

    def action_resume_reading(self):
        for record in self.filtered(lambda r: r.read_state == 'error' and r.read_queue):
            record.write({'read_state': 'queued', 'read_message': self.env._("Waiting for the background job.")})
        self.env.ref('om_tally_base.ir_cron_om_tally_read')._trigger()
        return True

    def _om_tally_set_remote_companies(self, companies):
        self.remote_company_ids = [Command.clear()] + [Command.create({
            'name': values['name'], 'guid': values.get('guid'), 'books_from': values.get('books_from'),
            'starting_from': values.get('starting_from'), 'currency_symbol': values.get('currency_symbol'),
        }) for values in companies]
        if len(companies) == 1 or (companies and not self.tally_company_name):
            self.remote_company_ids[:1].action_select()

    def _om_tally_after_sync(self, vouchers):
        """ Hook: the vouchers a sync created or changed. """
        return True

    # ------------------------------------------------------------------------------------------------------------
    # analysis

    def _om_tally_compute_problems(self):
        self.ensure_one()
        env = self.env
        self.problem_ids.unlink()
        problems = []

        def add(level, category, message, record=None):
            problems.append({'import_id': self.id, 'level': level, 'category': category, 'message': message,
                             'res_model': record._name if record else False, 'res_id': record.id if record else 0})

        ledgers = self.ledger_ids
        if not self.currency_id.is_zero(self.opening_difference):
            add('warning', env._("Opening balances"), env._(
                "The opening balances of Tally differ by %(amount)s (%(side)s). The difference goes to the account "
                "you choose for it.", amount=f"{abs(self.opening_difference):,.2f}",
                side=env._("debit") if self.opening_difference > 0 else env._("credit")))
        seen = defaultdict(list)
        for ledger in ledgers:
            key = ''.join(char for char in ledger.name.lower() if char.isalnum())
            seen[key].append(ledger)
        for same in seen.values():
            if len(same) > 1:
                add('warning', env._("Duplicate names"), env._(
                    "These ledgers look like the same one: %s", ", ".join(ledger.name for ledger in same)), same[0])
        country = self.tally_country
        label = self.tax_number_label
        for ledger in ledgers:
            if not ledger.group_id and ledger.role != 'pl':
                add('error', env._("Unknown group"), env._(
                    "Ledger %(ledger)s is under group %(group)s, which was not read.",
                    ledger=ledger.name, group=ledger.parent_name or '-'), ledger)
            if ledger.role in ('receivable', 'payable'):
                number = (ledger.tax_number or '').strip().upper()
                registered = ledger.gst_registration_type not in ('Unregistered', 'Consumer', 'Unknown')
                if country in ('in', 'ae', 'sa', 'bh') and not number and registered:
                    add('info', env._("Parties without %s", label), env._(
                        "%(party)s has no %(label)s.", party=ledger.name, label=label), ledger)
                elif number and country == 'in' and not GSTIN.match(number):
                    add('warning', env._("Tax numbers to check"), env._(
                        "The GSTIN %(number)s of %(party)s does not look right.", number=number, party=ledger.name),
                        ledger)
                elif number and country in ('ae', 'sa', 'bh') and not TRN.match(number):
                    add('warning', env._("Tax numbers to check"), env._(
                        "The %(label)s %(number)s of %(party)s should have 15 digits.", label=label, number=number,
                        party=ledger.name), ledger)
                if ledger.bill_ids and not self.currency_id.is_zero(ledger.bill_total - ledger.opening_balance):
                    add('warning', env._("Bill-wise openings"), env._(
                        "The opening bills of %(ledger)s add up to %(bills)s, its opening balance is %(opening)s: "
                        "the difference becomes an 'Opening balance' line.", ledger=ledger.name,
                        bills=f"{ledger.bill_total:,.2f}", opening=f"{ledger.opening_balance:,.2f}"), ledger)
            elif ledger.gstin or ledger.is_billwise:
                add('warning', env._("Ledgers in odd groups"), env._(
                    "%(ledger)s has a GSTIN or bill-wise details but is under %(group)s, not under Sundry Debtors or "
                    "Sundry Creditors: it becomes an account, not a partner.", ledger=ledger.name,
                    group=ledger.parent_name), ledger)
            elif ledger.role == 'account' and any(word in ledger.name.lower() for word in (' bank', 'bank ', ' a/c no')):
                add('info', env._("Ledgers in odd groups"), env._(
                    "%(ledger)s looks like a bank account but is under %(group)s.", ledger=ledger.name,
                    group=ledger.parent_name), ledger)
            if ledger.role == 'account' and ledger.nature in ('income', 'expense') and \
                    not self.currency_id.is_zero(ledger.opening_balance):
                add('warning', env._("Opening balances"), env._(
                    "%s is an income or expense ledger with an opening balance.", ledger.name), ledger)
        for item in env['om.tally.stock.item'].search([('import_id', '=', self.id)]):
            if item.opening_quantity < 0 or any(opening.quantity < 0 for opening in item.opening_ids):
                add('warning', env._("Negative stock"), env._("%s has a negative opening stock.", item.name), item)
            if not item.unit_id and item.base_unit_name:
                add('warning', env._("Unknown units"), env._("The unit %(unit)s of %(item)s was not read.",
                                                              unit=item.base_unit_name, item=item.name), item)
        vouchers = env['om.tally.voucher'].search([('import_id', '=', self.id)])
        for voucher in vouchers.filtered(lambda v: v.is_accounting):
            if not self.currency_id.is_zero(voucher.difference):
                add('error', env._("Unbalanced vouchers"), env._(
                    "%(voucher)s of %(date)s is off by %(amount)s.", voucher=voucher.display_number,
                    date=voucher.date, amount=f"{voucher.difference:,.2f}"), voucher)
            unknown = voucher.line_ids.filtered(lambda line: not line.ledger_id)
            if unknown:
                add('error', env._("Unknown ledgers"), env._(
                    "%(voucher)s uses ledgers that were not read: %(ledgers)s", voucher=voucher.display_number,
                    ledgers=", ".join(set(unknown.mapped('ledger_name')))), voucher)
        for voucher in vouchers.filtered(lambda v: not v.voucher_type_id):
            add('warning', env._("Unknown voucher types"), env._(
                "%(voucher)s is of type %(type)s, which was not read.", voucher=voucher.display_number,
                type=voucher.voucher_type_name), voucher)
        skipped = Counter()
        for voucher in vouchers.filtered(lambda v: not v.is_accounting):
            reason = (voucher.is_cancelled and env._("cancelled")) or (voucher.is_optional and env._("optional")) \
                or (voucher.is_postdated and env._("post-dated")) or (voucher.is_deleted and env._("deleted")) \
                or env._("not accounting (%s)", voucher.base_type or voucher.voucher_type_name)
            skipped[reason] += 1
        for reason, count in skipped.items():
            add('info', env._("Vouchers left out"), env._("%(count)s %(reason)s voucher(s) are not imported.",
                                                           count=count, reason=reason))
        if self.books_from and vouchers and vouchers[:1].date < self.books_from:
            add('warning', env._("Dates"), env._("Some vouchers are dated before the books beginning date %s.",
                                                  self.books_from))
        env['om.tally.problem'].create(problems)

    def _om_tally_analysis_html(self):
        self.ensure_one()
        env = self.env
        masters = [
            (env._("Groups"), self.group_count), (env._("Ledgers"), self.ledger_count - self.party_count),
            (env._("Parties"), self.party_count), (env._("Voucher Types"), self.voucher_type_count),
            (env._("Cost Centres"), self.cost_centre_count), (env._("Currencies"), self.currency_count),
            (env._("Units"), self.unit_count), (env._("Stock Items"), self.stock_item_count),
            (env._("Godowns"), self.godown_count),
        ]
        rows = env['om.tally.voucher']._read_group(
            [('import_id', '=', self.id)], ['base_type', 'fiscal_year'], ['__count', 'amount:sum'])
        years = sorted({year for _type, year, _count, _amount in rows if year})
        by_type = defaultdict(dict)
        for base_type, year, count, _amount in rows:
            by_type[base_type or env._("Unknown")][year] = count
        state_rows = dict(env['om.tally.voucher']._read_group(
            [('import_id', '=', self.id), ('is_accounting', '=', False)], ['base_type'], ['__count']))
        html = Markup('<div class="row">')
        html += Markup('<div class="col-lg-4"><h5>%s</h5><table class="table table-sm o_om_tally_table">') % \
            env._("Masters")
        for label, count in masters:
            html += Markup('<tr><td>%s</td><td class="text-end">%s</td></tr>') % (label, count)
        html += Markup('</table><h5>%s</h5><table class="table table-sm">') % env._("Company")
        for label, value in (
                (env._("Tally company"), self.tally_company_name or '-'),
                (env._("Books beginning from"), self.books_from or '-'),
                (env._("Financial year from"), self.starting_from or '-'),
                (env._("Total opening debit"), f"{self.opening_debit_total:,.2f}"),
                (env._("Total opening credit"), f"{self.opening_credit_total:,.2f}"),
                (env._("Difference in opening balances"), f"{self.opening_difference:,.2f}"),
        ):
            html += Markup('<tr><td>%s</td><td class="text-end">%s</td></tr>') % (label, value)
        html += Markup('</table></div><div class="col-lg-8"><h5>%s</h5>') % env._("Vouchers per type and year")
        html += Markup('<table class="table table-sm table-hover"><thead><tr><th>%s</th>') % env._("Voucher type")
        for year in years:
            html += Markup('<th class="text-end">%s</th>') % year
        html += Markup('<th class="text-end">%s</th><th class="text-end">%s</th></tr></thead><tbody>') % (
            env._("Total"), env._("Not imported"))
        totals = Counter()
        for base_type in sorted(by_type):
            counts = by_type[base_type]
            accounting = base_type in ACCOUNTING_VOUCHER_TYPES
            html += Markup('<tr><td>%s%s</td>') % (
                base_type, '' if accounting else Markup(' <span class="text-muted">(%s)</span>') % env._("no accounting"))
            for year in years:
                html += Markup('<td class="text-end">%s</td>') % (counts.get(year) or '')
                totals[year] += counts.get(year, 0)
            html += Markup('<td class="text-end fw-bold">%s</td><td class="text-end text-muted">%s</td></tr>') % (
                sum(counts.values()), state_rows.get(base_type) or '')
        html += Markup('</tbody><tfoot><tr class="fw-bold"><td>%s</td>') % env._("Total")
        for year in years:
            html += Markup('<td class="text-end">%s</td>') % totals[year]
        html += Markup('<td class="text-end">%s</td><td></td></tr></tfoot></table>') % sum(totals.values())
        levels = Counter(self.problem_ids.mapped('level'))
        html += Markup('<h5>%s</h5><p>') % env._("Problems")
        for level, css, label in (('error', 'danger', env._("errors")), ('warning', 'warning', env._("warnings")),
                                  ('info', 'info', env._("notes"))):
            html += Markup('<span class="badge text-bg-%s me-2">%s %s</span>') % (css, levels.get(level, 0), label)
        html += Markup('</p></div></div>')
        return html

    # ------------------------------------------------------------------------------------------------------------
    # actions

    def action_test_connection(self):
        self.ensure_one()
        if self.source_type != 'direct':
            raise UserError(self.env._("The test is for the direct connection."))
        try:
            companies = self._om_tally_client().companies()
        except TallyConnectionError as error:
            self._om_tally_log(str(error), 'error', 'connect')
            raise UserError(str(error)) from error
        if not companies:
            raise UserError(self.env._("Tally answers, but no company is open in it: open the company in Tally."))
        self._om_tally_set_remote_companies(companies)
        self._om_tally_log(self.env._("Connected to Tally: %s", ", ".join(c['name'] for c in companies)),
                           step='connect')
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'title': self.env._("Connected"),
                       'message': self.env._("Tally answers. Companies open: %s",
                                             ", ".join(c['name'] for c in companies)),
                       'next': {'type': 'ir.actions.act_window_close'}},
        }

    def action_read_tally(self, only_new=None):
        """ Read the masters and vouchers from the source into the staging tables, then analyze them. A big company
        is read in the background. Files already read are left out unless all are read again. """
        for record in self:
            new_only = record.state != 'draft' if only_new is None else only_new
            if record.read_state in ('queued', 'running'):
                raise UserError(self.env._("Tally is being read in the background already."))
            if record.read_background:
                record._om_tally_start_background_read(only_new=new_only)
                continue
            try:
                if record.source_type == 'file':
                    record._om_tally_read_files(only_new=new_only)
                else:
                    record._om_tally_read_direct()
            except TallyConnectionError as error:
                raise UserError(str(error)) from error
            record._om_tally_finish_read()
        return True

    def action_read_all_again(self):
        return self.action_read_tally(only_new=False)

    def action_analyze(self):
        for record in self:
            record._om_tally_link()
            record._om_tally_compute_problems()
            if record.state == 'draft':
                record.state = 'analyzed'
            record._om_tally_log(self.env._("Analyzed: %(ledgers)s ledgers, %(vouchers)s vouchers, %(problems)s "
                                            "problems.", ledgers=record.ledger_count, vouchers=record.voucher_count,
                                            problems=record.problem_count), step='analyze')
        return True

    def action_clear_staging(self):
        for record in self:
            for model in list(MASTER_MODELS.values()) + ['om.tally.voucher', 'om.tally.problem',
                                                         'om.tally.remote.company']:
                self.env[model].search([('import_id', '=', record.id)]).unlink()
            self.env['om.tally.period'].search([('import_id', '=', record.id)]).unlink()
            record.write({'state': 'draft', 'last_alter_id': 0, 'read_file_ids': [Command.clear()],
                          'read_state': 'idle', 'read_queue': False, 'read_offset': 0, 'read_total': 0,
                          'read_message': False})
            record._om_tally_log(self.env._("The data read from Tally was cleared."), step='read')
        return True

    def action_back_to_connect(self):
        self.write({'state': 'draft'})
        return True

    def _om_tally_open(self, model, name, domain=None, context=None):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': name, 'res_model': model, 'view_mode': 'list,form',
            'domain': [('import_id', '=', self.id)] + (domain or []),
            'context': dict({'default_import_id': self.id}, **(context or {})),
        }

    def action_open_groups(self):
        return self._om_tally_open('om.tally.group', self.env._("Groups"))

    def action_open_ledgers(self):
        return self._om_tally_open('om.tally.ledger', self.env._("Ledgers"),
                                   [('role', 'not in', ('receivable', 'payable'))])

    def action_open_parties(self):
        return self._om_tally_open('om.tally.ledger', self.env._("Parties"),
                                   [('role', 'in', ('receivable', 'payable'))])

    def action_open_vouchers(self):
        action = self._om_tally_open('om.tally.voucher', self.env._("Vouchers"))
        action['view_mode'] = 'list,pivot,graph,form'
        return action

    def action_open_voucher_types(self):
        return self._om_tally_open('om.tally.voucher.type', self.env._("Voucher Types"))

    def action_open_cost_centres(self):
        return self._om_tally_open('om.tally.cost.centre', self.env._("Cost Centres"))

    def action_open_stock_items(self):
        return self._om_tally_open('om.tally.stock.item', self.env._("Stock Items"))

    def action_open_godowns(self):
        return self._om_tally_open('om.tally.godown', self.env._("Godowns"))

    def action_open_units(self):
        return self._om_tally_open('om.tally.unit', self.env._("Units"))

    def action_open_currencies(self):
        return self._om_tally_open('om.tally.currency', self.env._("Currencies"))

    def action_open_problems(self):
        return self._om_tally_open('om.tally.problem', self.env._("Problems"))

    def action_open_mappings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': self.env._("Mappings"), 'res_model': 'om.tally.mapping',
            'view_mode': 'list,form', 'domain': [('company_id', '=', self.company_id.id)],
        }

    # ------------------------------------------------------------------------------------------------------------
    # sync

    @api.model
    def _cron_om_tally_sync(self):
        """ Read what changed in Tally since the last Alter ID, for the direct connections that keep in sync. """
        records = self.search([('sync_enabled', '=', True), ('source_type', '=', 'direct')])
        for record in records:
            try:
                record._om_tally_fetch_changes()
            except (TallyConnectionError, UserError) as error:
                record._om_tally_log(self.env._("Sync failed: %s", error), 'error', 'sync')
            self.env['ir.cron']._commit_progress(1)

    def _om_tally_fetch_changes(self):
        self.ensure_one()
        client = self._om_tally_client()
        masters, _data = client.masters(self.tally_company_name)
        self._om_tally_stage(masters)
        last = self.env['om.tally.voucher'].search([('import_id', '=', self.id)], order='alter_id desc', limit=1)
        objects, _data = client.vouchers_altered_after(self.tally_company_name, last.alter_id or 0)
        vouchers = self._om_tally_stage(objects)
        self._om_tally_link()
        self._om_tally_log(self.env._("Sync: %s new or changed vouchers.", len(vouchers)), step='sync')
        if vouchers:
            self._om_tally_after_sync(vouchers)
        return vouchers

    def action_sync_now(self):
        for record in self:
            if record.source_type != 'direct':
                raise UserError(self.env._("The sync reads Tally over the direct connection: for files, add the "
                                           "export of the new period and read it."))
            record._om_tally_fetch_changes()
        return True

    # sample data

    def action_load_sample_files(self):
        """ Attach the sample export of Tally shipped with the module, to try the import. """
        self.ensure_one()
        attachments = self.env['ir.attachment']
        for file_name in ('tally_company.xml', 'tally_masters.xml', 'tally_vouchers.xml'):
            with file_open(f'om_tally_base/data/sample/{file_name}', 'rb') as file:
                attachments |= attachments.create({
                    'name': file_name, 'raw': file.read(),
                    'res_model': self._name, 'res_id': self.id, 'mimetype': 'application/xml',
                })
        self.write({'source_type': 'file', 'file_ids': [Command.link(a.id) for a in attachments]})
        return True
