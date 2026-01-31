# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from odoo import api, models

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    def _remove_data(self, to_remove_models, seq_prefixes=None):
        if not self.env.user.has_group('base.group_system'):
            return False
        seq_prefixes = seq_prefixes or []
        for model_name in to_remove_models:
            try:
                if not self.env['ir.model']._get(model_name):
                    continue
            except Exception as e:
                _logger.warning('remove data error get ir.model: %s, %s', model_name, e)
                continue
            try:
                model = self.env[model_name]
                if not model._auto:
                    continue
                table_name = model._table
            except KeyError:
                _logger.warning('model not in registry, skip: %s', model_name)
                continue
            except Exception as e:
                _logger.warning('remove data error get model table: %s, %s', model_name, e)
                continue
            try:
                # table_name from model._table (registry), safe for format
                self.env.cr.execute("DELETE FROM %s" % table_name)
                self.env.cr.commit()
            except Exception as e:
                _logger.warning('remove data error: %s, %s', model_name, e)
        for prefix in seq_prefixes:
            domain = [
                '|', ('code', '=ilike', prefix + '%'), ('prefix', '=ilike', prefix + '%')
            ]
            try:
                seqs = self.env['ir.sequence'].sudo().search(domain)
                if seqs:
                    seqs.write({'number_next': 1})
            except Exception as e:
                _logger.warning('reset sequence data error: %s, %s', prefix, e)
        return True

    def remove_sales(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = ['sale.order.line', 'sale.order']
        seqs = ['sale']
        return self._remove_data(to_removes, seqs)

    def remove_product(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = ['product.product', 'product.template']
        seqs = ['product.product']
        return self._remove_data(to_removes, seqs)

    def remove_product_attribute(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = ['product.attribute.value', 'product.attribute']
        return self._remove_data(to_removes, [])

    def remove_pos(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = [
            'pos.payment',
            'pos.order.line',
            'pos.order',
            'pos.session',
        ]
        seqs = ['pos.']
        res = self._remove_data(to_removes, seqs)
        try:
            if 'account.bank.statement' in self.env:
                statements = self.env['account.bank.statement'].sudo().search([])
                for stmt in statements:
                    if hasattr(stmt, '_compute_balance_end'):
                        stmt._compute_balance_end()
        except Exception as e:
            _logger.error('reset balance after pos remove: %s', e)
        return res

    def remove_purchase(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = [
            'purchase.order.line',
            'purchase.order',
            'purchase.requisition.line',
            'purchase.requisition',
        ]
        seqs = ['purchase.']
        return self._remove_data(to_removes, seqs)

    def remove_expense(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = [
            'hr.expense.sheet',
            'hr.expense',
            'hr.payslip',
            'hr.payslip.run',
        ]
        seqs = ['hr.expense.']
        return self._remove_data(to_removes, seqs)

    def remove_mrp(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = [
            'mrp.workcenter.productivity',
            'mrp.workorder',
            'mrp.routing.workcenter',
            'change.production.qty',
            'mrp.production',
            'mrp.production.product.line',
            'mrp.unbuild',
        ]
        if 'sale.forecast' in self.env:
            to_removes.extend(['sale.forecast.indirect', 'sale.forecast'])
        seqs = ['mrp.']
        return self._remove_data(to_removes, seqs)

    def remove_mrp_bom(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = ['mrp.bom.line', 'mrp.bom']
        return self._remove_data(to_removes, [])

    def remove_inventory(self):
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

    def remove_account(self):
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
            ('prefix', '=ilike', '杂项/%'),
        ]
        try:
            seqs = self.env['ir.sequence'].search(domain)
            if seqs:
                seqs.write({'number_next': 1})
        except Exception as e:
            _logger.error('reset sequence data error: %s', e)
        return res

    def remove_account_chart(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        company = self.env.company
        self = self.with_company(company)
        to_removes = [
            'res.partner.bank',
            'account.move.line',
            'account.payment',
            'account.bank.statement',
            'account.tax.account.tag',
            'account.tax',
            'account.account.tag',
            'account.journal',
            'account.account',
        ]
        if 'wizard_multi_charts_accounts' in self.env:
            to_removes.append('wizard_multi_charts_accounts')
        try:
            field_ids = self.env['ir.model.fields']._get_ids('product.template')
            field1 = field_ids.get('taxes_id')
            field2 = field_ids.get('supplier_taxes_id')
            if field1 and field2:
                self.env.cr.execute(
                    "DELETE FROM ir_default WHERE (field_id = %s OR field_id = %s) AND company_id = %s",
                    (field1, field2, company.id),
                )
            self.env.cr.execute(
                "UPDATE account_journal SET bank_account_id = NULL WHERE company_id = %s",
                (company.id,),
            )
            self.env.cr.commit()
        except Exception as e:
            _logger.error('remove data error account_chart ir_default/journal: %s', e)
        if self.env['ir.model']._get_id('pos.config'):
            try:
                self.env['pos.config'].write({'journal_id': False})
            except Exception:
                pass
        try:
            for r in self.env['res.partner'].search([]):
                r.write({
                    'property_account_receivable_id': False,
                    'property_account_payable_id': False,
                })
        except Exception as e:
            _logger.error('remove data error account_chart partner: %s', e)
        try:
            for r in self.env['product.category'].search([]):
                r.write({
                    'property_account_income_categ_id': False,
                    'property_account_expense_categ_id': False,
                    'property_account_creditor_price_difference_categ': False,
                    'property_stock_account_input_categ_id': False,
                    'property_stock_account_output_categ_id': False,
                    'property_stock_valuation_account_id': False,
                })
        except Exception:
            pass
        try:
            for r in self.env['product.template'].search([]):
                r.write({
                    'property_account_income_id': False,
                    'property_account_expense_id': False,
                })
        except Exception:
            pass
        try:
            for r in self.env['stock.location'].search([]):
                r.write({
                    'valuation_in_account_id': False,
                    'valuation_out_account_id': False,
                })
        except Exception:
            pass
        return self._remove_data(to_removes, [])

    def remove_project(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = [
            'account.analytic.line',
            'project.task',
            'project.project',
        ]
        if 'project.forecast' in self.env:
            to_removes.insert(-1, 'project.forecast')
        return self._remove_data(to_removes, [])

    def remove_quality(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = ['quality.check', 'quality.alert']
        seqs = ['quality.check', 'quality.alert']
        return self._remove_data(to_removes, seqs)

    def remove_quality_setting(self):
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
        return self._remove_data(to_removes, [])

    def remove_website(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = [
            'blog.tag.category',
            'blog.tag',
            'blog.post',
            'blog.blog',
            'product.wishlist',
            'website.visitor',
            'website.redirect',
            'website.seo.metadata',
        ]
        return self._remove_data(to_removes, [])

    def remove_message(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        to_removes = [
            'mail.message',
            'mail.followers',
            'mail.activity',
        ]
        return self._remove_data(to_removes, [])

    def remove_all(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        self.remove_account()
        self.remove_quality()
        self.remove_website()
        self.remove_quality_setting()
        self.remove_inventory()
        self.remove_purchase()
        self.remove_mrp()
        self.remove_sales()
        self.remove_project()
        self.remove_pos()
        self.remove_expense()
        self.remove_account_chart()
        self.remove_message()
        return True

    def reset_cat_loc_name(self):
        for rec in self.env['product.category'].search([
            ('parent_id', '!=', False)
        ], order='complete_name'):
            try:
                rec._compute_complete_name()
            except Exception:
                pass
        try:
            for rec in self.env['stock.location'].search([
                ('location_id', '!=', False),
                ('usage', '!=', 'views'),
            ], order='complete_name'):
                rec._compute_complete_name()
        except Exception:
            pass
        return True
