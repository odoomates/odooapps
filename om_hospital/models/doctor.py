from odoo import _, api, fields, models


class HospitalDoctor(models.Model):
    _name = 'hospital.doctor'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Hospital Doctor'
    _rec_name = 'doctor_name'
    _order = 'doctor_name'

    doctor_name = fields.Char(string='Name', required=True, tracking=True)
    gender = fields.Selection([('male', 'Male'), ('female', 'Female'), ('other', 'Other')],
                              required=True, default='male', tracking=True)
    speciality = fields.Char()
    note = fields.Text(string='Description')
    image = fields.Binary(string='Photo')
    active = fields.Boolean(default=True)
    appointment_ids = fields.One2many('hospital.appointment', 'doctor_id', string='Appointments')
    appointment_count = fields.Integer(compute='_compute_appointment_count')

    @api.depends('appointment_ids')
    def _compute_appointment_count(self):
        counts = {doctor.id: count for doctor, count in self.env['hospital.appointment']._read_group(
            [('doctor_id', 'in', self.ids)], ['doctor_id'], ['__count'])}
        for doctor in self:
            doctor.appointment_count = counts.get(doctor.id, 0)

    def copy_data(self, default=None):
        values = super().copy_data(default)
        if 'doctor_name' not in (default or {}):
            for doctor, vals in zip(self, values):
                vals['doctor_name'] = _("%s (copy)", doctor.doctor_name)
        return values
