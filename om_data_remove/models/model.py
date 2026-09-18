import logging
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

# the models each removal deletes, in the order they are deleted
REMOVAL_MODELS = {
    'sales': [
        'sale.order.line',
        'sale.order',
    ],
    'product': [
        'product.product',
        'product.template',
    ],
    'product_attribute': [
        'product.attribute.value',
        'product.attribute',
    ],
    'pos': [
        'pos.payment',
        'pos.order.line',
        'pos.order',
        'pos.session',
    ],
    'purchase': [
        'purchase.order.line',
        'purchase.order',
        'purchase.requisition.line',
        'purchase.requisition',
    ],
    'expense': [
        'hr.expense.sheet',
        'hr.expense',
        'hr.payslip',
        'hr.payslip.run',
    ],
    'mrp': [
        'mrp.workcenter.productivity',
        'mrp.workorder',
        'mrp.production.workcenter.line',
        'change.production.qty',
        'mrp.production',
        'mrp.production.product.line',
        'mrp.unbuild',
        'change.production.qty',
        'sale.forecast.indirect',
        'sale.forecast',
    ],
    'mrp_bom': [
        'mrp.bom.line',
        'mrp.bom',
    ],
    'inventory': [
        'stock.quant',
        'stock.move.line',
        'stock.package_level',
        'stock.quantity.history',
        'stock.quant.package',
        'stock.move',
        'stock.picking',
        'stock.scrap',
        'stock.picking.batch',
        'stock.inventory.line',
        'stock.inventory',
        'stock.valuation.layer',
        'stock.production.lot',
        'procurement.group',
    ],
    'account': [
        'payment.transaction',
        'account.bank.statement.line',
        'account.bank.statement',
        'account.payment',
        'account.analytic.line',
        'account.analytic.account',
        'account.partial.reconcile',
        'account.move.line',
        'hr.expense.sheet',
        'account.move',
    ],
    'account_chart': [
        'res.partner.bank',
        'account.move.line',
        'account.invoice',
        'account.payment',
        'account.bank.statement',
        'account.tax.account.tag',
        'account.tax',
        'account.account.account.tag',
        'wizard_multi_charts_accounts',
        'account.journal',
        'account.account',
    ],
    'project': [
        'account.analytic.line',
        'project.task',
        'project.forecast',
        'project.project',
    ],
    'quality': [
        'quality.check',
        'quality.alert',
    ],
    'quality_setting': [
        'quality.point',
        'quality.alert.stage',
        'quality.alert.team',
        'quality.point.test_type',
        'quality.reason',
        'quality.tag',
    ],
    'website': [
        'blog.tag.category',
        'blog.tag',
        'blog.post',
        'blog.blog',
        'product.wishlist',
        'website.published.multi.mixin',
        'website.published.mixin',
        'website.multi.mixin',
        'website.visitor',
        'website.redirect',
        'website.seo.metadata',
    ],
    'message': [
        'mail.message',
        'mail.followers',
        'mail.activity',
    ],
}

# what the Data Cleaning screen offers: key, section, label
REMOVAL_GROUPS = [
    ('all', 'Everything', 'All the transactions, the master data kept'),
    ('sales', 'Sales', 'Sales orders'),
    ('pos', 'Sales', 'Point of Sale orders and sessions'),
    ('purchase', 'Purchases and Expenses', 'Purchase orders and requisitions'),
    ('expense', 'Purchases and Expenses', 'Expenses and expense reports'),
    ('mrp', 'Manufacturing', 'Manufacturing orders'),
    ('mrp_bom', 'Manufacturing', 'Bills of materials'),
    ('inventory', 'Inventory', 'Moves, transfers, packages and lots'),
    ('account', 'Accounting', 'Journal entries, invoices, bills and payments'),
    ('account_chart', 'Accounting', 'Chart of accounts, taxes and journals'),
    ('project', 'Projects', 'Projects and tasks'),
    ('quality', 'Quality', 'Quality checks and alerts'),
    ('quality_setting', 'Quality', 'Quality control points'),
    ('website', 'Website', 'Website pages and blog posts'),
    ('product', 'Master Data', 'Products'),
    ('product_attribute', 'Master Data', 'Product attributes'),
    ('message', 'Master Data', 'Messages, followers and activities'),
]
# what Delete All removes, see _remove_all
ALL_GROUPS = ['account', 'quality', 'website', 'quality_setting', 'inventory', 'purchase', 'mrp', 'sales', 'project',
              'pos', 'expense', 'account_chart', 'message']
CONFIRMATION_WORD = 'DELETE'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # the number of records each removal would delete
    for _key, _section, _label in REMOVAL_GROUPS:
        locals()['om_remove_count_%s' % _key] = fields.Integer(
            string=_label, compute='_compute_om_remove_counts')
    del _key, _section, _label

    @api.model
    def _om_removal_models(self, key):
        keys = ALL_GROUPS if key == 'all' else [key]
        return [model for group in keys for model in REMOVAL_MODELS[group] if model in self.env]

    @api.model
    def _om_removal_count(self, key):
        return sum(
            self.env[model].sudo().with_context(active_test=False).search_count([])
            for model in self._om_removal_models(key)
            if not self.env[model]._abstract
        )

    def _compute_om_remove_counts(self):
        counts = {}
        if self.env.user.has_group('base.group_system'):
            counts = {key: self._om_removal_count(key) for key, _section, _label in REMOVAL_GROUPS}
        for settings in self:
            for key, _section, _label in REMOVAL_GROUPS:
                settings['om_remove_count_%s' % key] = counts.get(key, 0)

    def action_om_open_removal(self):
        """ Ask for the confirmation of the removal given in the context """
        key = self.env.context.get('om_removal')
        if key not in dict((group[0], group) for group in REMOVAL_GROUPS):
            raise UserError(_('Unknown removal.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Delete Data'),
            'res_model': 'om.data.remove.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_removal': key},
        }

    def _remove_data(self, o, s=[]):
        if not self.env.user.has_group('base.group_system'):
            return False
        for line in o:
            try:
                if not self.env['ir.model']._get(line):
                    continue
            except Exception as e:
                _logger.warning('remove data error get ir.model: %s,%s', line, e)
                continue
            obj_name = line
            obj = self.pool.get(obj_name)
            if not obj:
                t_name = obj_name.replace('.', '_')
            else:
                t_name = obj._table
            sql = "delete from %s" % t_name
            try:
                self.env.cr.execute(sql)
                self.env.cr.commit()
            except Exception as e:
                # a failed statement leaves the transaction aborted: without this
                # rollback every later statement of the loop fails too, and the
                # removal silently stops after the first error
                self.env.cr.rollback()
                _logger.warning('remove data error: %s,%s', line, e)
        for line in s:
            domain = ['|', ('code', '=ilike', line + '%'), ('prefix', '=ilike', line + '%')]
            try:
                seqs = self.env['ir.sequence'].sudo().search(domain)
                if seqs.exists():
                    seqs.write({
                        'number_next': 1,
                    })
            except Exception as e:
                _logger.warning('reset sequence data error: %s,%s', line, e)
        return True

    def _remove_sales(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = list(REMOVAL_MODELS['sales'])
        seqs = [
            'sale',
        ]
        return self._remove_data(to_removes, seqs)

    def _remove_product(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = list(REMOVAL_MODELS['product'])
        seqs = [
            'product.product',
        ]
        return self._remove_data(to_removes, seqs)

    def _remove_product_attribute(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = list(REMOVAL_MODELS['product_attribute'])
        seqs = []
        return self._remove_data(to_removes, seqs)

    def _remove_pos(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = list(REMOVAL_MODELS['pos'])
        seqs = [
            'pos.',
        ]
        res = self._remove_data(to_removes, seqs)
        self._recompute_bank_statement_balances()
        return res

    def _recompute_bank_statement_balances(self):
        """ The rows are deleted in SQL, behind the ORM: the stored balances of the bank statements left are
        computed again from the lines they still have. """
        try:
            statements = self.env['account.bank.statement'].sudo().search([])
            if not statements:
                return
            statements.invalidate_recordset()
            for name in ('balance_start', 'balance_end', 'balance_end_real'):
                field = statements._fields.get(name)
                if field and field.store and field.compute:
                    self.env.add_to_compute(field, statements)
            statements.flush_recordset()
        except Exception as e:
            _logger.error('bank statement balance error: %s', e)

    def _remove_purchase(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = list(REMOVAL_MODELS['purchase'])
        seqs = [
            'purchase.',
        ]
        return self._remove_data(to_removes, seqs)

    def _remove_expense(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = list(REMOVAL_MODELS['expense'])
        seqs = [
            'hr.expense.',
        ]
        return self._remove_data(to_removes, seqs)

    def _remove_mrp(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = list(REMOVAL_MODELS['mrp'])
        seqs = [
            'mrp.',
        ]
        return self._remove_data(to_removes, seqs)

    def _remove_mrp_bom(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = list(REMOVAL_MODELS['mrp_bom'])
        seqs = []
        return self._remove_data(to_removes, seqs)

    def _remove_inventory(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = list(REMOVAL_MODELS['inventory'])
        seqs = [
            'stock.',
            'picking.',
            'procurement.group',
            'product.tracking.default',
            'WH/',
        ]
        return self._remove_data(to_removes, seqs)

    def _remove_account(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = list(REMOVAL_MODELS['account'])
        res = self._remove_data(to_removes, [])
        domain = [
            ('company_id', '=', self.env.company.id),
            '|', ('code', '=ilike', 'account.%'),
            '|', ('prefix', '=ilike', 'BNK1/%'),
            '|', ('prefix', '=ilike', 'CSH1/%'),
            '|', ('prefix', '=ilike', 'INV/%'),
            '|', ('prefix', '=ilike', 'EXCH/%'),
            '|', ('prefix', '=ilike', 'MISC/%'),
            '|', ('prefix', '=ilike', '账单/%'),
            ('prefix', '=ilike', '杂项/%')
        ]
        try:
            seqs = self.env['ir.sequence'].search(domain)
            if seqs.exists():
                seqs.write({
                    'number_next': 1,
                })
        except Exception as e:
            _logger.error('reset sequence data error: %s,%s', domain, e)
        return res

    def _remove_account_chart(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        company_id = self.env.company.id
        self = self.with_context(force_company=company_id, company_id=company_id)
        to_removes = list(REMOVAL_MODELS['account_chart'])
        try:
            field1 = self.env['ir.model.fields']._get('product.template', "taxes_id").id
            field2 = self.env['ir.model.fields']._get('product.template', "supplier_taxes_id").id

            sql = "delete from ir_default where (field_id = %s or field_id = %s) and company_id=%d" \
                  % (field1, field2, company_id)
            sql2 = "update account_journal set bank_account_id=NULL where company_id=%d;" % company_id
            self.env.cr.execute(sql)
            self.env.cr.execute(sql2)

            self.env.cr.commit()
        except Exception as e:
            # reset the aborted transaction, see above
            self.env.cr.rollback()
            _logger.error('remove data error: %s,%s', 'account_chart: set tax and account_journal', e)
        if self.env['ir.model']._get('pos.config'):
            self.env['pos.config'].write({
                'journal_id': False,
            })
        try:
            rec = self.env['res.partner'].search([])
            for r in rec:
                r.write({
                    'property_account_receivable_id': None,
                    'property_account_payable_id': None,
                })
        except Exception as e:
            _logger.error('remove data error: %s,%s', 'account_chart', e)
        try:
            rec = self.env['product.category'].search([])
            for r in rec:
                r.write({
                    'property_account_income_categ_id': None,
                    'property_account_expense_categ_id': None,
                    'property_account_creditor_price_difference_categ': None,
                    'property_stock_account_input_categ_id': None,
                    'property_stock_account_output_categ_id': None,
                    'property_stock_valuation_account_id': None,
                })
        except Exception as e:
            pass
        try:
            rec = self.env['product.template'].search([])
            for r in rec:
                r.write({
                    'property_account_income_id': None,
                    'property_account_expense_id': None,
                })
        except Exception as e:
            pass
        try:
            rec = self.env['stock.location'].search([])
            for r in rec:
                r.write({
                    'valuation_in_account_id': None,
                    'valuation_out_account_id': None,
                })
        except Exception as e:
            pass
        seqs = []
        res = self._remove_data(to_removes, seqs)
        return res

    def _remove_project(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = list(REMOVAL_MODELS['project'])
        seqs = []
        return self._remove_data(to_removes, seqs)

    def _remove_quality(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = list(REMOVAL_MODELS['quality'])
        seqs = [
            'quality.check',
            'quality.alert',
        ]
        return self._remove_data(to_removes, seqs)

    def _remove_quality_setting(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = list(REMOVAL_MODELS['quality_setting'])
        return self._remove_data(to_removes)

    def _remove_website(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = list(REMOVAL_MODELS['website'])
        seqs = []
        return self._remove_data(to_removes, seqs)

    def _remove_message(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = list(REMOVAL_MODELS['message'])
        seqs = []
        return self._remove_data(to_removes, seqs)

    def action_remove_all(self):
        self._remove_all()

    def action_remove_sales(self):
        self._remove_sales()

    def action_remove_pos(self):
        self._remove_pos()

    def action_remove_purchase(self):
        self._remove_purchase()

    def action_remove_expense(self):
        self._remove_expense()

    def action_remove_mrp(self):
        self._remove_mrp()

    def action_remove_mrp_bom(self):
        self._remove_mrp_bom()

    def action_remove_inventory(self):
        self._remove_inventory()

    def action_remove_account(self):
        self._remove_account()

    def action_remove_account_chart(self):
        self._remove_account_chart()

    def action_remove_project(self):
        self._remove_project()

    def action_remove_quality(self):
        self._remove_quality()

    def action_remove_quality_setting(self):
        self._remove_quality_setting()

    def action_remove_website(self):
        self._remove_website()

    def action_remove_product(self):
        self._remove_product()

    def action_remove_product_attribute(self):
        self._remove_product_attribute()

    def action_remove_message(self):
        self._remove_message()

    def _remove_all(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        self.action_remove_account()
        self.action_remove_quality()
        self.action_remove_website()
        self.action_remove_quality_setting()
        self.action_remove_inventory()
        self.action_remove_purchase()
        self.action_remove_mrp()
        self.action_remove_sales()
        self.action_remove_project()
        self.action_remove_pos()
        self.action_remove_expense()
        self.action_remove_account_chart()
        self.action_remove_message()
        return True

    def reset_cat_loc_name(self):
        ids = self.env['product.category'].search([
            ('parent_id', '!=', False)
        ], order='complete_name')
        for rec in ids:
            try:
                rec._compute_complete_name()
            except:
                pass
        try:
            ids = self.env['stock.location'].search([
                ('location_id', '!=', False),
                ('usage', '!=', 'views'),
            ], order='complete_name')
            for rec in ids:
                rec._compute_complete_name()
        except:
            pass
        return True


class OmDataRemoveWizard(models.TransientModel):
    """ The confirmation of a removal: the data are deleted only once the user typed the confirmation word """
    _name = 'om.data.remove.wizard'
    _description = 'Delete Data'

    removal = fields.Selection([(key, label) for key, _section, label in REMOVAL_GROUPS], required=True,
                               readonly=True)
    record_count = fields.Integer(string='Records', compute='_compute_record_count')
    model_names = fields.Char(string='Tables', compute='_compute_record_count')
    confirmation = fields.Char(
        string='Confirmation', help='Type %s to confirm that the data are deleted for good.' % CONFIRMATION_WORD)

    @api.depends('removal')
    def _compute_record_count(self):
        settings = self.env['res.config.settings']
        for wizard in self:
            wizard.record_count = settings._om_removal_count(wizard.removal) if wizard.removal else 0
            names = settings._om_removal_models(wizard.removal) if wizard.removal else []
            wizard.model_names = ', '.join(self.env['ir.model']._get(name).name or name for name in names)

    def action_remove(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Only the administrators can delete data.'))
        if (self.confirmation or '').strip().upper() != CONFIRMATION_WORD:
            raise UserError(_('Type %s to confirm the removal.', CONFIRMATION_WORD))
        settings = self.env['res.config.settings'].create({})
        getattr(settings, 'action_remove_%s' % self.removal)()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('The data were deleted.'),
                'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }
