from odoo import api, fields, models
from odoo.exceptions import UserError


class FileExportWizard(models.TransientModel):
    """ Export the records selected with a layout: preview the file and its problems, then download it. """
    _name = 'file.export.wizard'
    _description = 'Export a File'

    layout_id = fields.Many2one('file.layout', required=True,
                                domain="[('model', '=', res_model)]")
    res_model = fields.Char(required=True)
    res_ids = fields.Json(required=True)
    record_count = fields.Integer(compute='_compute_preview')
    line_count = fields.Integer(compute='_compute_preview', string='Lines')
    total = fields.Float(compute='_compute_preview')
    preview = fields.Text(compute='_compute_preview')
    problems = fields.Text(compute='_compute_preview')
    has_problems = fields.Boolean(compute='_compute_preview')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        context = self.env.context
        values.setdefault('res_model', context.get('active_model'))
        values.setdefault('res_ids', context.get('active_ids') or (
            [context['active_id']] if context.get('active_id') else []))
        return values

    def _get_records(self):
        self.ensure_one()
        records = self.env[self.res_model].browse(self.res_ids or [])
        records.check_access('read')
        return records

    @api.depends('layout_id', 'res_ids')
    def _compute_preview(self):
        for wizard in self:
            wizard.record_count = len(wizard.res_ids or [])
            if not wizard.layout_id or not wizard.res_ids or wizard.layout_id.model != wizard.res_model:
                wizard.update({'line_count': 0, 'total': 0.0, 'preview': False, 'problems': False,
                               'has_problems': False})
                continue
            result = wizard.layout_id._render(wizard._get_records())
            wizard.update({
                'line_count': result['line_count'],
                'total': result['total'],
                'preview': result['preview'],
                'problems': '\n'.join(result['problems']) or False,
                'has_problems': bool(result['problems']),
            })

    def _export(self):
        """ :return: the export of the file, kept with its records """
        self.ensure_one()
        if not self.res_ids:
            raise UserError(self.env._('Select the records to export first.'))
        records = self._get_records()
        layout = self.layout_id
        result = layout._render(records)
        name = layout._get_file_name()
        export = self.env['file.export'].create({
            'name': name,
            'layout_id': layout.id,
            'res_model': self.res_model,
            'res_ids': records.ids,
            'record_count': len(records),
            'line_count': result['line_count'],
            'total': result['total'],
            'problems': '\n'.join(result['problems']) or False,
        })
        # the export stays as it was made: its users read it, they do not change it
        export.sudo().attachment_id = self.env['ir.attachment'].sudo().create({
            'name': name,
            'raw': result['content'],
            'res_model': export._name,
            'res_id': export.id,
        })
        if hasattr(records, '_file_exported'):
            records._file_exported(export)
        return export

    def action_download(self):
        return self._export().action_download()
