from odoo import api, models, _


# How To Call A Python Function While Printing PDF Report in Odoo
# https://www.youtube.com/watch?v=JGWc1KjyIBk&list=PLqRRLx0cl0hoJhjFWkFYowveq2Zn55dhM&index=62
class PatientCardReport(models.AbstractModel):
    _name = 'report.om_hospital.report_patient'
    _description = 'Patient card Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['hospital.patient'].browse(docids[0])
        appointments = self.env['hospital.appointment'].search([('patient_id', '=', docids[0])])
        appointment_list = []
        for app in appointments:
            vals = {
                'name': app.name,
                'notes': app.notes,
                'appointment_date': app.appointment_date
            }
            appointment_list.append(vals)
        return {
            'doc_model': 'hospital.patient',
            'docs': docs,
            'appointment_list': appointment_list,
        }
