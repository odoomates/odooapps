from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_adaptive_learning = fields.Boolean(
        string='Learn from usage', config_parameter='om_adaptive_views.learning', default=True)
    om_adaptive_days = fields.Integer(
        string='Weeks of usage looked at (days)', config_parameter='om_adaptive_views.days', default=90)
    om_adaptive_min_saves = fields.Integer(
        string='Saves before folding', config_parameter='om_adaptive_views.min_saves', default=100)
    om_adaptive_fade_rate = fields.Float(
        string='Fold below (%)', config_parameter='om_adaptive_views.fade_rate', default=2.0)
    om_adaptive_promote_rate = fields.Float(
        string='Bring forward from (%)', config_parameter='om_adaptive_views.promote_rate', default=80.0)
    om_adaptive_max_folds = fields.Integer(
        string='Folds per form at most', config_parameter='om_adaptive_views.max_folds', default=10)
    om_adaptive_fill_guard = fields.Float(
        string='Keep fields filled on more than (%)', config_parameter='om_adaptive_views.fill_guard', default=50.0)
    om_adaptive_min_visits = fields.Integer(
        string='Visits before a filter change', config_parameter='om_adaptive_views.min_visits', default=50)
    om_adaptive_filter_rate = fields.Float(
        string='Default filter from (%)', config_parameter='om_adaptive_views.filter_rate', default=70.0)
    om_adaptive_min_column_toggles = fields.Integer(
        string='Column switches before a change', config_parameter='om_adaptive_views.min_column_toggles', default=5)
    om_adaptive_protected_models = fields.Char(
        string='Models left alone', config_parameter='om_adaptive_views.protected_models',
        default='account.move,account.payment,account.bank.statement,res.users,res.company',
        help="Technical names of models, separated by commas.")
    om_adaptive_protected_fields = fields.Char(
        string='Fields always kept', config_parameter='om_adaptive_views.protected_fields',
        help="Field names, or model.field, separated by commas.")
    om_adapt_role_ids = fields.Many2many(related='company_id.om_adapt_role_ids', readonly=False)
    om_adaptive_auto_apply = fields.Boolean(
        string='Apply clear changes on their own', config_parameter='om_adaptive_views.auto_apply')
    om_adaptive_auto_min_saves = fields.Integer(
        string='Saves before folding on its own', config_parameter='om_adaptive_views.auto_min_saves', default=300)
    om_adaptive_auto_fade_rate = fields.Float(
        string='Fold on its own below (%)', config_parameter='om_adaptive_views.auto_fade_rate', default=1.0)
    om_adaptive_auto_min_visits = fields.Integer(
        string='Visits before a default filter on its own', config_parameter='om_adaptive_views.auto_min_visits',
        default=150)
    om_adaptive_auto_filter_rate = fields.Float(
        string='Default filter on its own from (%)', config_parameter='om_adaptive_views.auto_filter_rate',
        default=85.0)
    om_adaptive_user_filters = fields.Boolean(
        string='Personal default filters', config_parameter='om_adaptive_views.user_filters', default=True)
    om_adaptive_user_min_visits = fields.Integer(
        string='Visits of a person before their default filter',
        config_parameter='om_adaptive_views.user_min_visits', default=20)
    om_adaptive_user_filter_rate = fields.Float(
        string='Their default filter from (%)', config_parameter='om_adaptive_views.user_filter_rate', default=70.0)
    om_adaptive_menu_order = fields.Boolean(
        string='Menu order', config_parameter='om_adaptive_views.menu_order', default=True)
    om_adaptive_min_menu_opens = fields.Integer(
        string='Opens before reordering', config_parameter='om_adaptive_views.min_menu_opens', default=50)
    om_adaptive_menu_ratio = fields.Float(
        string='Moves up when opened (times) more', config_parameter='om_adaptive_views.menu_ratio', default=1.5)
    om_adaptive_user_menus = fields.Boolean(
        string='Personal menu order', config_parameter='om_adaptive_views.user_menus', default=True)
    om_adaptive_user_min_menu_opens = fields.Integer(
        string='Opens of a person before their order',
        config_parameter='om_adaptive_views.user_min_menu_opens', default=30)
    om_adapt_pinned_menu_ids = fields.Many2many(related='company_id.om_adapt_pinned_menu_ids', readonly=False)

    def action_om_adaptive_reset(self):
        """ Start learning again from nothing: the counts, the reports and the suggestions
        not acted on go. Applied and dismissed changes stay. """
        company = self.env.company
        self.env['om.usage.stat'].sudo().search([('company_id', '=', company.id)]).unlink()
        self.env['om.usage.user.stat'].sudo().search([('company_id', '=', company.id)]).unlink()
        self.env['om.adapt.field.report'].sudo().search([('company_id', '=', company.id)]).unlink()
        self.env['om.adapt.menu.report'].sudo().search([('company_id', '=', company.id)]).unlink()
        self.env['om.adapt.rule'].sudo().search(
            [('company_id', '=', company.id), ('state', '=', 'suggested')]).unlink()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': self.env._("Adaptive Views starts learning again."),
                       'next': {'type': 'ir.actions.act_window_close'}},
        }
