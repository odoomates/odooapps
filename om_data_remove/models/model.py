import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

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
                self._cr.execute(sql)
                self._cr.commit()
            except Exception as e:
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
        to_removes = [
            'sale.order.line',
            'sale.order',
        ]
        seqs = [
            'sale',
        ]
        return self._remove_data(to_removes, seqs)

    def _remove_product(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = [
            'product.product',
            'product.template',
        ]
        seqs = [
            'product.product',
        ]
        return self._remove_data(to_removes, seqs)

    def _remove_product_attribute(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = [
            'product.attribute.value',
            'product.attribute',
        ]
        seqs = []
        return self._remove_data(to_removes, seqs)

    def _remove_pos(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = [
            'pos.payment',
            'pos.order.line',
            'pos.order',
            'pos.session',
        ]
        seqs = [
            'pos.',
        ]
        res = self._remove_data(to_removes, seqs)
        try:
            statement = self.env['account.bank.statement'].sudo().search([])
            for s in statement:
                s._end_balance()
        except Exception as e:
            _logger.error('reset sequence data error: %s', e)
        return res

    def _remove_purchase(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = [
            'purchase.order.line',
            'purchase.order',
            'purchase.requisition.line',
            'purchase.requisition',
        ]
        seqs = [
            'purchase.',
        ]
        return self._remove_data(to_removes, seqs)

    def _remove_expense(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = [
            'hr.expense.sheet',
            'hr.expense',
            'hr.payslip',
            'hr.payslip.run',
        ]
        seqs = [
            'hr.expense.',
        ]
        return self._remove_data(to_removes, seqs)

    def _remove_mrp(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = [
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
        ]
        seqs = [
            'mrp.',
        ]
        return self._remove_data(to_removes, seqs)

    def _remove_mrp_bom(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = [
            'mrp.bom.line',
            'mrp.bom',
        ]
        seqs = []
        return self._remove_data(to_removes, seqs)

    def _remove_inventory(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = [
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
        ]
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
        to_removes = [
            'payment.transaction',
            'account.bank.statement.line',
            'account.payment',
            'account.analytic.line',
            'account.analytic.account',
            'account.partial.reconcile',
            'account.move.line',
            'hr.expense.sheet',
            'account.move',
        ]
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
        to_removes = [
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
        ]
        try:
            field1 = self.env['ir.model.fields']._get('product.template', "taxes_id").id
            field2 = self.env['ir.model.fields']._get('product.template', "supplier_taxes_id").id

            sql = "delete from ir_default where (field_id = %s or field_id = %s) and company_id=%d" \
                  % (field1, field2, company_id)
            sql2 = "update account_journal set bank_account_id=NULL where company_id=%d;" % company_id
            self._cr.execute(sql)
            self._cr.execute(sql2)

            self._cr.commit()
        except Exception as e:
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
        to_removes = [
            'account.analytic.line',
            'project.task',
            'project.forecast',
            'project.project',
        ]
        seqs = []
        return self._remove_data(to_removes, seqs)

    def _remove_quality(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = [
            'quality.check',
            'quality.alert',
        ]
        seqs = [
            'quality.check',
            'quality.alert',
        ]
        return self._remove_data(to_removes, seqs)

    def _remove_quality_setting(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = [
            'quality.point',
            'quality.alert.stage',
            'quality.alert.team',
            'quality.point.test_type',
            'quality.reason',
            'quality.tag',
        ]
        return self._remove_data(to_removes)

    def _remove_website(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = [
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
        ]
        seqs = []
        return self._remove_data(to_removes, seqs)

    def _remove_message(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = [
            'mail.message',
            'mail.followers',
            'mail.activity',
        ]
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
