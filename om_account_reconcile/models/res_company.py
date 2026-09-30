from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_reconcile_auto = fields.Boolean(
        string='Reconcile New Transactions Automatically', default=True,
        help='When bank or cash transactions are created or imported, apply the automatic reconciliation models '
             'and reconcile the transactions matching exactly one open item by amount and reference.')
