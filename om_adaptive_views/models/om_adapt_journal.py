from odoo import fields, models


class OmAdaptJournal(models.Model):
    """ Every change applied, undone or dismissed: who, when, and on what numbers. """
    _name = 'om.adapt.journal'
    _description = 'Screen change journal'
    _order = 'id desc'

    rule_id = fields.Many2one('om.adapt.rule', string='Screen change', ondelete='set null', index=True)
    name = fields.Char(string='Change', required=True)
    event = fields.Selection([
        ('apply', 'Applied'),
        ('auto', 'Applied on its own'),
        ('undo', 'Undone'),
        ('dismiss', 'Dismissed'),
        ('import', 'Imported'),
    ], required=True)
    user_id = fields.Many2one('res.users', string='By', default=lambda self: self.env.user, ondelete='set null')
    company_id = fields.Many2one('res.company', ondelete='cascade')
    model_label = fields.Char(string='Model name')
    group_id = fields.Many2one('res.groups', string='Role', ondelete='set null')
    target_user_id = fields.Many2one('res.users', string='For user', ondelete='set null')
    evidence = fields.Char()
    uses = fields.Integer()
    total = fields.Integer()
