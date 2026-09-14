from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    asset_gain_account_id = fields.Many2one(
        'account.account', string='Gain Account on Asset Sale', check_company=True,
        help="Account used to book the gain when an asset is sold above its book value.",
    )
    asset_loss_account_id = fields.Many2one(
        'account.account', string='Loss Account on Asset Disposal', check_company=True,
        help="Account used to book the loss when an asset is sold below its book value or disposed of.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    asset_gain_account_id = fields.Many2one(
        related='company_id.asset_gain_account_id', readonly=False,
    )
    asset_loss_account_id = fields.Many2one(
        related='company_id.asset_loss_account_id', readonly=False,
    )
