from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class HospitalAppointment(models.Model):
    _name = 'hospital.appointment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Hospital Appointment'
    _order = 'date_appointment desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    patient_id = fields.Many2one('hospital.patient', required=True, tracking=True, ondelete='restrict')
    doctor_id = fields.Many2one('hospital.doctor', required=True, tracking=True)
    age = fields.Integer(related='patient_id.age')
    gender = fields.Selection(related='patient_id.gender')
    date_appointment = fields.Datetime(string='Date', default=fields.Datetime.now, required=True)
    duration = fields.Float(default=0.5, help="In hours.")
    priority = fields.Selection([('0', 'Normal'), ('1', 'Low'), ('2', 'High'), ('3', 'Very High')], default='0')
    state = fields.Selection([('draft', 'Draft'), ('confirm', 'Confirmed'), ('done', 'Done'), ('cancel', 'Cancelled')],
                             string='Status', default='draft', required=True, tracking=True)
    note = fields.Text(string='Description')
    prescription = fields.Html()
    prescription_line_ids = fields.One2many('appointment.prescription.line', 'appointment_id', string='Medicines')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    fee = fields.Monetary(currency_field='currency_id')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hospital.appointment') or _('New')
        return super().create(vals_list)

    @api.onchange('patient_id')
    def _onchange_patient_id(self):
        if self.patient_id.note and not self.note:
            self.note = self.patient_id.note

    @api.constrains('duration')
    def _check_duration(self):
        if any(appointment.duration <= 0 for appointment in self):
            raise ValidationError(_("The duration of an appointment must be positive."))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_done(self):
        if any(appointment.state == 'done' for appointment in self):
            raise UserError(_("You cannot delete an appointment that is done."))

    def action_confirm(self):
        self.write({'state': 'confirm'})

    def action_done(self):
        self.write({'state': 'done'})
        return {'effect': {'fadeout': 'slow', 'message': _("Appointment done!"), 'type': 'rainbow_man'}}

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_cancel(self):
        cancel_days = int(self.env['ir.config_parameter'].sudo().get_param('om_hospital.cancel_days', 0))
        for appointment in self:
            if cancel_days and appointment.date_appointment and \
                    (appointment.date_appointment - fields.Datetime.now()).days < cancel_days:
                raise UserError(_("An appointment can be cancelled %s days before its date only.", cancel_days))
        self.write({'state': 'cancel'})

    def action_notify(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _("Reminder"), 'message': _("Appointment %s is sent to the patient.", self.name),
                       'type': 'success', 'sticky': False},
        }


class AppointmentPrescriptionLine(models.Model):
    _name = 'appointment.prescription.line'
    _description = 'Appointment Prescription Line'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    name = fields.Char(string='Medicine', required=True)
    qty = fields.Integer(string='Quantity', default=1)
    appointment_id = fields.Many2one('hospital.appointment', required=True, ondelete='cascade')
