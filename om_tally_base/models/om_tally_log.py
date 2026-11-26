from odoo import api, fields, models


class OmTallyLog(models.Model):
    _name = 'om.tally.log'
    _description = 'Tally Import Log'
    _order = 'id desc'

    import_id = fields.Many2one('om.tally.import', required=True, ondelete='cascade', index=True)
    date = fields.Datetime(default=fields.Datetime.now, required=True)
    level = fields.Selection([('info', 'Info'), ('warning', 'Warning'), ('error', 'Error')], default='info',
                             required=True)
    step = fields.Char()
    message = fields.Text(required=True)
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user)


class OmTallyProblem(models.Model):
    """ What the analysis found that the user should look at before importing. """
    _name = 'om.tally.problem'
    _description = 'Tally Data Problem'
    _order = 'level_sequence, category, id'

    import_id = fields.Many2one('om.tally.import', required=True, ondelete='cascade', index=True)
    level = fields.Selection([('info', 'Info'), ('warning', 'Warning'), ('error', 'Error')], default='warning',
                             required=True)
    level_sequence = fields.Integer(compute='_compute_level_sequence', store=True)
    category = fields.Char(required=True)
    message = fields.Text(required=True)
    res_model = fields.Char(string='Model')
    res_id = fields.Many2oneReference(string='Record ID', model_field='res_model')

    @api.depends('level')
    def _compute_level_sequence(self):
        for problem in self:
            problem.level_sequence = {'error': 1, 'warning': 2, 'info': 3}.get(problem.level, 4)

    def action_open_record(self):
        self.ensure_one()
        if not self.res_model or not self.res_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'target': 'new',
        }
