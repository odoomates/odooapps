""" Remember what the Studio created.

While the Studio is open, its calls carry the om_pen_studio context key. Every
record of these models created then gets an external id under __om_pen__, which is how
the export tells the Studio's work from what modules made.
"""
from odoo import api, models

MARK_MODULE = '__om_pen__'
MARK_PREFIX = 'pen_'


class OmPenMarked(models.AbstractModel):
    _name = 'om.pen.marked'
    _description = "Records Made In Pen Studio"

    @api.model
    def _om_pen_mark(self, records):
        if not records or not self.env.context.get('om_pen_studio'):
            return
        self.env['ir.model.data'].sudo().create([{
            'module': MARK_MODULE,
            'name': '%s%s_%s' % (MARK_PREFIX, record._name.replace('.', '_'), record.id),
            'model': record._name,
            'res_id': record.id,
            'noupdate': True,
        } for record in records])


def _marking(model_name):
    class Marked(models.Model):
        _inherit = model_name

        @api.model_create_multi
        def create(self, vals_list):
            records = super().create(vals_list)
            self.env['om.pen.marked']._om_pen_mark(records)
            return records
    Marked.__name__ = 'OmPenMarked_%s' % model_name.replace('.', '_')
    return Marked


for _model in ('ir.model', 'ir.model.fields', 'ir.ui.view', 'ir.actions.act_window', 'ir.actions.server',
               'ir.actions.report', 'ir.ui.menu', 'res.groups', 'ir.access'):
    globals()['Marked_%s' % _model.replace('.', '_')] = _marking(_model)
