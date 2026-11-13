from odoo import _, api, fields, models


class CreateAppointmentWizard(models.TransientModel):
    _name = 'create.appointment.wizard'
    _description = 'Create Appointment Wizard'

    patient_id = fields.Many2one('hospital.patient', required=True)
    doctor_id = fields.Many2one('hospital.doctor', required=True)
    date_appointment = fields.Datetime(string='Date', default=fields.Datetime.now, required=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if self.env.context.get('active_model') == 'hospital.patient' and self.env.context.get('active_id'):
            values['patient_id'] = self.env.context['active_id']
        return values

    def action_create_appointment(self):
        appointment = self.env['hospital.appointment'].create({
            'patient_id': self.patient_id.id,
            'doctor_id': self.doctor_id.id,
            'date_appointment': self.date_appointment,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Appointment'),
            'res_model': 'hospital.appointment',
            'res_id': appointment.id,
            'view_mode': 'form',
        }
