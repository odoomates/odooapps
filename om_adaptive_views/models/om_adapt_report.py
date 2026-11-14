from odoo import api, fields, models
from odoo.tools import SQL


class OmAdaptFieldReport(models.Model):
    """ Every field of every form saved in the period, with how often it was changed.

    Rebuilt by each analysis: a picture of the last weeks, not a history.
    """
    _name = 'om.adapt.field.report'
    _description = 'Field usage'
    _order = 'model, share, field_label'

    company_id = fields.Many2one('res.company', required=True, index=True, ondelete='cascade')
    model = fields.Char(required=True, index=True)
    model_label = fields.Char(string='Model name')
    view_id = fields.Many2one('ir.ui.view', ondelete='cascade')
    field_name = fields.Char(string='Field', required=True)
    field_label = fields.Char(string='Label')
    page_label = fields.Char(string='Tab')
    # per form, so adding them up across fields means nothing
    saves = fields.Integer(aggregator=None)
    edits = fields.Integer(string='Changed', aggregator=None)
    share = fields.Float(string='Changed in (%)', digits=(16, 1), aggregator=None)
    history = fields.Char(string='Weekly use')
    last_used = fields.Date()
    status = fields.Selection([
        ('unused', 'Never changed'),
        ('rare', 'Rarely changed'),
        ('used', 'In use'),
        ('kept', 'Kept'),
    ])
    kept_reason = fields.Char(string='Why kept')
    foldable = fields.Boolean()
    rule_state = fields.Selection([
        ('suggested', 'Suggested'), ('applied', 'Folded'), ('dismissed', 'Dismissed'),
    ], string='Fold', compute='_compute_rule_state')

    def _om_rule(self):
        self.ensure_one()
        return self.env['om.adapt.rule'].sudo().search([
            ('company_id', '=', self.company_id.id), ('kind', '=', 'fade_field'), ('model', '=', self.model),
            ('view_id', '=', self.view_id.id), ('element', '=', self.field_name),
            ('group_id', '=', False), ('user_id', '=', False),
        ], limit=1)

    def _compute_rule_state(self):
        for row in self:
            row.rule_state = row._om_rule().state if row.id else False

    def action_fold(self):
        """ Fold the field now, whatever the thresholds say: the admin has seen the numbers. """
        Rules = self.env['om.adapt.rule']
        rules = Rules.browse()
        for row in self.filtered('foldable'):
            rule = row._om_rule() or Rules.sudo().create({
                'company_id': row.company_id.id, 'kind': 'fade_field', 'model': row.model,
                'view_id': row.view_id.id, 'element': row.field_name, 'element_label': row.field_label,
                'uses': row.edits, 'total': row.saves, 'score': row.share, 'history': row.history,
                'last_used': row.last_used,
                'evidence': self.env._("Changed in %(used)s of %(saved)s saves", used=row.edits, saved=row.saves),
            })
            rules |= rule
        rules.action_apply()
        return True

    def action_unfold(self):
        for row in self:
            row._om_rule().action_undo()
        return True

    @api.model
    def _om_rebuild(self, company, rows):
        labels = {model.model: model.name for model in self.env['ir.model'].sudo().search(
            [('model', 'in', list({row['model'] for row in rows}))])}
        self.sudo().search([('company_id', '=', company.id)]).unlink()
        self.sudo().create([dict(row, company_id=company.id, model_label=labels.get(row['model'], row['model']))
                            for row in rows])


class OmAdaptMenuReport(models.Model):
    """ Every menu that opens something, with how often it was opened in the period. """
    _name = 'om.adapt.menu.report'
    _description = 'Menu usage'
    _order = 'opens, complete_name'

    company_id = fields.Many2one('res.company', required=True, index=True, ondelete='cascade')
    menu_id = fields.Many2one('ir.ui.menu', string='Menu item', required=True, ondelete='cascade')
    complete_name = fields.Char(string='Menu')
    opens = fields.Integer(aggregator='sum')
    history = fields.Char(string='Weekly use')
    last_used = fields.Date()

    def action_open_menu(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'ir.ui.menu', 'res_id': self.menu_id.id,
            'view_mode': 'form', 'target': 'current',
        }

    @api.model
    def _om_rebuild(self, company, since):
        Stats = self.env['om.usage.stat']
        opens = {}
        for (_model, _view, _action, element, _event), count in Stats._om_totals(
                company, since, 'menu', ['menu']).items():
            if element.isdigit():
                opens[int(element)] = opens.get(int(element), 0) + count
        weekly = {int(key[3]): value for key, value in Stats._om_weekly(company, 'menu', ['menu']).items()
                  if key[3].isdigit()}
        self.sudo().search([('company_id', '=', company.id)]).unlink()
        menus = self.env['ir.ui.menu'].sudo().search([('action', '!=', False)])
        self.sudo().create([{
            'company_id': company.id, 'menu_id': menu.id, 'complete_name': menu.complete_name,
            'opens': opens.get(menu.id, 0),
            'history': weekly.get(menu.id, ('[]', False))[0],
            'last_used': weekly.get(menu.id, ('[]', False))[1],
        } for menu in menus])
