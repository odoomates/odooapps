from odoo import _, fields, models


class SearchAppointmentWizard(models.TransientModel):
    _name = 'search.appointment.wizard'
    _description = 'Search Appointment Wizard'

    patient_id = fields.Many2one('hospital.patient', required=True)

    def action_search_ref(self):
        """ The action of the menu, read by its external id, with a domain. """
        action = self.env['ir.actions.actions']._for_xml_id('om_hospital.action_hospital_appointment')
        action['domain'] = [('patient_id', '=', self.patient_id.id)]
        action['context'] = {}
        return action

    def action_search_dict(self):
        """ The same, written as a dictionary. """
        return {
            'type': 'ir.actions.act_window',
            'name': _('Appointments'),
            'res_model': 'hospital.appointment',
            'view_mode': 'tree,form',
            'domain': [('patient_id', '=', self.patient_id.id)],
        }
