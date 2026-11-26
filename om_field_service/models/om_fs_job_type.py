from random import randint

from odoo import api, fields, models


class OmFsJobType(models.Model):
    _name = 'om.fs.job.type'
    _description = "Field Service Job Type"
    _order = 'sequence, name'

    def _default_color(self):
        return randint(1, 11)

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(default=_default_color)
    description = fields.Text(string="Instructions", translate=True,
                              help="Shown to the technician on the job.")
    default_duration = fields.Float(
        string="Default Duration", default=1.0,
        help="Hours planned for a job of this type (the allocated time of the job).")
    role_id = fields.Many2one(
        'om.planning.role', string="Planning Role",
        domain="[('is_field_service', '=', True)]",
        help="Technicians suggested for the jobs of this type: the resources of this role. "
             "Empty: every field service role.")
    checklist_line_ids = fields.One2many('om.fs.job.type.check', 'job_type_id', string="Checklist", copy=True)
    signature_required = fields.Boolean(
        string="Signature Required", help="The job can only be marked as done once the customer signed it.")
    checklist_required = fields.Boolean(
        string="Complete Checklist Required",
        help="The job can only be marked as done once the required checklist items are filled in.")
    company_id = fields.Many2one('res.company', string="Company")
    job_count = fields.Integer(compute='_compute_job_count', string="Jobs")

    def _compute_job_count(self):
        counts = dict(self.env['project.task']._read_group(
            [('job_type_id', 'in', self.ids)], ['job_type_id'], ['__count']))
        for job_type in self:
            job_type.job_count = counts.get(job_type, 0)

    def action_view_jobs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_field_service.action_om_fs_job')
        action['domain'] = [('job_type_id', '=', self.id)]
        action['context'] = {'default_job_type_id': self.id}
        return action


class OmFsJobTypeCheck(models.Model):
    _name = 'om.fs.job.type.check'
    _description = "Field Service Checklist Template Line"
    _order = 'sequence, id'

    job_type_id = fields.Many2one('om.fs.job.type', string="Job Type", required=True, ondelete='cascade',
                                  index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Item", required=True, translate=True)
    check_type = fields.Selection([
        ('check', 'Check Box'),
        ('text', 'Text'),
        ('number', 'Number'),
    ], string="Type", required=True, default='check')
    required = fields.Boolean(string="Required")
    uom_label = fields.Char(string="Unit", help="Unit of a number, e.g. bar, V, °C.")

    @api.model
    def _fs_line_values(self):
        return [{
            'name': line.name,
            'sequence': line.sequence,
            'check_type': line.check_type,
            'required': line.required,
            'uom_label': line.uom_label,
        } for line in self]
