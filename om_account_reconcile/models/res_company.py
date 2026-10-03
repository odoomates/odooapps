from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # the root company of Odoo 17 and later: Odoo 16 only has the parent companies
    root_id = fields.Many2one('res.company', compute='_compute_root_id')

    def _compute_root_id(self):
        for company in self:
            root = company
            while root.parent_id:
                root = root.parent_id
            company.root_id = root

    om_reconcile_auto = fields.Boolean(
        string='Reconcile New Transactions Automatically', default=True,
        help='When bank or cash transactions are created or imported, apply the automatic reconciliation models '
             'and reconcile the transactions matching exactly one open item by amount and reference.')
