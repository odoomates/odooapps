from odoo import fields, models


class FileExport(models.Model):
    """ A file exported with a layout, kept as it was sent: who exported it, when, and for which records. """
    _name = 'file.export'
    _description = 'File Export'
    _check_company_auto = True
    _order = 'create_date desc, id desc'

    name = fields.Char(string='File', required=True, readonly=True)
    layout_id = fields.Many2one('file.layout', required=True, readonly=True, index=True,
                                ondelete='restrict', check_company=True)
    res_model = fields.Char(string='Model', readonly=True)
    res_ids = fields.Json(string='Records', readonly=True)
    record_count = fields.Integer(string='Records Exported', readonly=True)
    line_count = fields.Integer(string='Lines', readonly=True)
    total = fields.Float(readonly=True)
    problems = fields.Text(readonly=True)
    attachment_id = fields.Many2one('ir.attachment', string='File Content', readonly=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True, default=lambda self: self.env.company)

    def action_download(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % self.attachment_id.id,
            'target': 'download',
        }

    def action_open_records(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Records of %s', self.name),
            'res_model': self.res_model,
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.res_ids or [])],
        }
