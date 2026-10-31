from odoo import fields, models


class PrintMixin(models.AbstractModel):
    """ A record printed from print templates, with a smart button on what was issued for it. """
    _name = 'print.mixin'
    _description = 'Print Mixin'

    print_issue_count = fields.Integer(string='Issued Prints', compute='_compute_print_issue_count')

    def _compute_print_issue_count(self):
        counts = dict(self.env['print.issue']._read_group(
            [('res_model', '=', self._name), ('res_id', 'in', self.ids), ('state', '!=', 'draft')],
            ['res_id'], ['__count']))
        for record in self:
            record.print_issue_count = counts.get(record.id, 0)

    def action_open_print_issues(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Prints of %s', self.display_name),
            'res_model': 'print.issue',
            'view_mode': 'list,form',
            'domain': [('res_model', '=', self._name), ('res_id', '=', self.id)],
            'context': {'create': False},
        }
