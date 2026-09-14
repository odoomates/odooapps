from odoo import api, fields, models, tools


class AssetAssetReport(models.Model):
    _name = "asset.asset.report"
    _description = "Assets Analysis"
    _auto = False

    name = fields.Char(string='Year', required=False, readonly=True)
    date = fields.Date(readonly=True)
    depreciation_date = fields.Date(string='Depreciation Date', readonly=True)
    asset_id = fields.Many2one('account.asset.asset', string='Asset', readonly=True)
    asset_category_id = fields.Many2one('account.asset.category', string='Asset category', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    state = fields.Selection([('draft', 'Draft'), ('open', 'Running'), ('paused', 'Paused'), ('close', 'Close')], string='Status', readonly=True)
    depreciation_value = fields.Float(string='Amount of Depreciation Lines', readonly=True)
    installment_value = fields.Float(string='Amount of Installment Lines', readonly=True)
    move_check = fields.Boolean(string='Posted', readonly=True)
    installment_nbr = fields.Integer(string='Installment Count', readonly=True)
    depreciation_nbr = fields.Integer(string='Depreciation Count', readonly=True)
    gross_value = fields.Float(string='Gross Amount', readonly=True)
    posted_value = fields.Float(string='Posted Amount', readonly=True)
    unposted_value = fields.Float(string='Unposted Amount', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, 'asset_asset_report')
        self.env.cr.execute("""
            create or replace view asset_asset_report as (
                select
                    m.id as id,
                    m.ref as name,
                    m.date as depreciation_date,
                    a.date as date,
                    (CASE WHEN m.id = first_move.id
                      THEN a.value
                      ELSE 0
                      END) as gross_value,
                    m.asset_depreciation_amount as depreciation_value,
                    m.asset_depreciation_amount as installment_value,
                    (CASE WHEN m.state = 'posted'
                      THEN m.asset_depreciation_amount
                      ELSE 0
                      END) as posted_value,
                    (CASE WHEN m.state = 'draft'
                      THEN m.asset_depreciation_amount
                      ELSE 0
                      END) as unposted_value,
                    a.id as asset_id,
                    (m.state = 'posted') as move_check,
                    a.category_id as asset_category_id,
                    a.partner_id as partner_id,
                    a.state as state,
                    1 as installment_nbr,
                    1 as depreciation_nbr,
                    a.company_id as company_id
                from account_move m
                    join account_asset_asset a on a.id = m.depreciation_asset_id
                    join (
                        select depreciation_asset_id as asset_id, min(id) as id
                          from account_move
                         where asset_entry_type in ('depreciation', 'revaluation') and state != 'cancel'
                         group by depreciation_asset_id
                    ) first_move on first_move.asset_id = a.id
                where a.active is true
                  and a.state != 'cancelled'
                  and m.state != 'cancel'
                  and m.asset_entry_type in ('depreciation', 'revaluation')
        )""")
