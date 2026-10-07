from odoo import _, api, models, fields
from odoo.exceptions import ValidationError


class AccountFinancialReport(models.Model):
    _name = "account.financial.report"
    _description = "Account Report"

    @api.depends('parent_id', 'parent_id.level')
    def _get_level(self):
        '''Returns a dictionary with key=the ID of a record and value = the level of this
           record in the tree structure.'''
        for report in self:
            level = 0
            if report.parent_id:
                level = report.parent_id.level + 1
            report.level = level

    def _get_children_by_order(self):
        res = self
        # the id after the sequence: the sections without one keep the order they were created in
        children = self.search([('parent_id', 'in', self.ids)], order='sequence ASC, id ASC')
        if children:
            for child in children:
                res += child._get_children_by_order()
        return res

    name = fields.Char('Report Name', required=True, translate=True)
    parent_id = fields.Many2one('account.financial.report', 'Parent')
    children_ids = fields.One2many('account.financial.report', 'parent_id', 'Account Report')
    sequence = fields.Integer('Sequence')
    level = fields.Integer(compute='_get_level', string='Level', store=True, recursive=True)
    type = fields.Selection([
        ('sum', 'View'),
        ('accounts', 'Accounts'),
        ('account_type', 'Account Type'),
        ('account_report', 'Report Value'),
        ], 'Type', default='sum')
    account_ids = fields.Many2many(
        'account.account', 'account_account_financial_report',
        'report_line_id', 'account_id', 'Accounts'
    )
    account_report_id = fields.Many2one('account.financial.report', 'Report Value')
    account_type_ids = fields.Many2many(
        'account.account.type', 'account_account_financial_report_type',
        'report_id', 'account_type_id', 'Account Types'
    )
    report_domain = fields.Char(string="Report Domain")
    sign = fields.Selection(
        [('-1', 'Reverse balance sign'), ('1', 'Preserve balance sign')], 'Sign on Reports',
        required=True, default='1',
        help='For accounts that are typically more debited than credited and that you would '
             'like to print as negative amounts in your reports, you should reverse the sign '
             'of the balance; e.g.: Expense account. The same applies for accounts that are '
             'typically more credited than debited and that you would like to print as positive '
             'amounts in your reports; e.g.: Income account.'
    )
    display_detail = fields.Selection([
        ('no_detail', 'No detail'),
        ('detail_flat', 'Display children flat'),
        ('detail_with_hierarchy', 'Display children with hierarchy')
        ], 'Display details', default='detail_flat')
    style_overwrite = fields.Selection([
        ('0', 'Automatic formatting'),
        ('1', 'Main Title 1 (bold, underlined)'),
        ('2', 'Title 2 (bold)'),
        ('3', 'Title 3 (bold, smaller)'),
        ('4', 'Normal Text'),
        ('5', 'Italic Text (smaller)'),
        ('6', 'Smallest Text'),
        ], 'Financial Report Style', default='0',
        help="You can set up here the format you want this record to be displayed. "
             "If you leave the automatic formatting, it will be computed based on the "
             "financial reports hierarchy (auto-computed field 'level').")
    children_ids = fields.One2many('account.financial.report', 'parent_id', string='Children')

    @api.constrains('parent_id')
    def _check_parent_id(self):
        if self._has_cycle():
            raise ValidationError(_('A section of a financial report cannot be placed under itself or under one of its sub-sections.'))

    def _get_amount_sources(self):
        """ The sections the amount of this one is computed from """
        self.ensure_one()
        if self.type == 'sum':
            return self.children_ids
        if self.type == 'account_report':
            return self.account_report_id
        return self.browse()

    @api.constrains('type', 'account_report_id', 'parent_id')
    def _check_amount_sources(self):
        # the report computes the amount of a View from its children and the amount of a Report Value
        # from the section it names: a section whose amount comes back to itself would never end
        for report in self:
            seen = set()
            todo = report._get_amount_sources()
            while todo:
                section = todo[0]
                todo = todo[1:]
                if section == report:
                    raise ValidationError(_(
                        'The amount of the section "%s" depends on itself: a Report Value cannot name the '
                        'section itself, nor a section that sums it.', report.name))
                if section.id not in seen:
                    seen.add(section.id)
                    todo |= section._get_amount_sources()
