from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HospitalPatient(models.Model):
    _name = 'hospital.patient'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Hospital Patient'
    _order = 'id desc'
    _rec_names_search = ['name', 'reference']

    name = fields.Char(required=True, tracking=True)
    reference = fields.Char(required=True, copy=False, readonly=True, default=lambda self: _('New'))
    date_of_birth = fields.Date()
    age = fields.Integer(compute='_compute_age', store=True, tracking=True)
    gender = fields.Selection([('male', 'Male'), ('female', 'Female'), ('other', 'Other')],
                              required=True, default='male', tracking=True)
    note = fields.Text(string='Description')
    image = fields.Binary(string='Photo')
    active = fields.Boolean(default=True)
    responsible_id = fields.Many2one('res.partner', string='Responsible')
    tag_ids = fields.Many2many('patient.tag', string='Tags')
    appointment_ids = fields.One2many('hospital.appointment', 'patient_id', string='Appointments')
    appointment_count = fields.Integer(compute='_compute_appointment_count')

    _sql_constraints = [
        ('reference_unique', 'unique (reference)', "This reference is already used by another patient."),
    ]

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if 'note' in fields_list and not values.get('note'):
            values['note'] = _('New patient')
        return values

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', _('New')) == _('New'):
                vals['reference'] = self.env['ir.sequence'].next_by_code('hospital.patient') or _('New')
        return super().create(vals_list)

    @api.depends('date_of_birth')
    def _compute_age(self):
        today = fields.Date.today()
        for patient in self:
            born = patient.date_of_birth
            patient.age = today.year - born.year - ((today.month, today.day) < (born.month, born.day)) if born else 0

    @api.depends('appointment_ids')
    def _compute_appointment_count(self):
        counts = {patient.id: count for patient, count in self.env['hospital.appointment']._read_group(
            [('patient_id', 'in', self.ids)], ['patient_id'], ['__count'])}
        for patient in self:
            patient.appointment_count = counts.get(patient.id, 0)

    @api.depends('name', 'reference')
    def _compute_display_name(self):
        for patient in self:
            patient.display_name = '[%s] %s' % (patient.reference, patient.name) if patient.reference else patient.name

    @api.constrains('date_of_birth')
    def _check_date_of_birth(self):
        for patient in self:
            if patient.date_of_birth and patient.date_of_birth > fields.Date.today():
                raise ValidationError(_("The date of birth of %s is in the future.", patient.name))

    def action_open_appointments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Appointments'),
            'res_model': 'hospital.appointment',
            'view_mode': 'tree,form,calendar',
            'domain': [('patient_id', '=', self.id)],
            'context': {'default_patient_id': self.id},
        }
