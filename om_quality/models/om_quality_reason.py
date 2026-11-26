from odoo import fields, models


class OmQualityReason(models.Model):
    _name = 'om.quality.reason'
    _description = 'Quality Failure Reason'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(string='Color Index')
    description = fields.Text(translate=True)


class OmQualityAlertStage(models.Model):
    _name = 'om.quality.alert.stage'
    _description = 'Non-conformance Stage'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(translate=True)
    fold = fields.Boolean(string='Folded in Kanban')
    is_closed = fields.Boolean(
        string='Closing Stage',
        help="Non-conformances in this stage are closed: the close date is set.")
    team_ids = fields.Many2many(
        'om.quality.team', 'om_quality_stage_team_rel', 'stage_id', 'team_id', string='Teams',
        help="Teams using this stage. A stage without team is proposed to new teams.")


class OmQualityTag(models.Model):
    _name = 'om.quality.tag'
    _description = 'Quality Tag'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    color = fields.Integer(string='Color Index')
