# -*- coding: utf-8 -*-

from odoo import models, fields


class CreateAppointment(models.TransientModel):
    _name = 'create.appointment'
    _description = 'Create Appointment Wizard'

    patient_id = fields.Many2one('hospital.patient', string="Patient")
    appointment_date = fields.Date(string="Appointment Date")

    def print_report(self):
        data = {
            'model': 'create.appointment',
            'form': self.read()[0]
        }
        # if data['form']['patient_id']:
        #     selected_patient = data['form']['patient_id'][0]
        #     appointments = self.env['hospital.appointment'].search([('patient_id', '=', selected_patient)])
        # else:
        #     appointments = self.env['hospital.appointment'].search([])
        # appointment_list = []
        # for app in appointments:
        #     vals = {
        #         'name': app.name,
        #         'notes': app.notes,
        #         'appointment_date': app.appointment_date
        #     }
        #     appointment_list.append(vals)
        # # print("appointments", appointments)
        # data['appointments'] = appointment_list
        # # print("Data", data)
        return self.env.ref('om_hospital.report_appointment').report_action(self, data=data)

    def delete_patient(self):
        for rec in self:
            rec.patient_id.unlink()
            # print("Test". rec)

    # Create Record From Code
    # https://www.youtube.com/watch?v=Jssb15ADeyg&list=PLqRRLx0cl0hoJhjFWkFYowveq2Zn55dhM&index=40
    def create_appointment(self):
        vals = {
            'patient_id': self.patient_id.id,
            'appointment_date': self.appointment_date,
            'notes': 'Created From The Wizard/Code'
        }
        # adding a message to the chatter from code
        # https://www.youtube.com/watch?v=J3MvgwHnR0A&list=PLqRRLx0cl0hoJhjFWkFYowveq2Zn55dhM&index=48
        self.patient_id.message_post(body="Test string ", subject="Appointment Creation")
        # creating appointments from the code
        self.env['hospital.appointment'].create(vals)

    # Fetching/ Taking Data From Database Tables
    # https://www.youtube.com/watch?v=hUPSvL8GTQE&list=PLqRRLx0cl0hoJhjFWkFYowveq2Zn55dhM&index=49
    def get_data(self):
        appointments = self.env['hospital.appointment'].search([])
        for rec in appointments:
            print("Appointment Name", rec.name)
        # How to Prevent Wizard Getting Closed After Button Click
        # https://www.youtube.com/watch?v=n5La3aTue7o&list=PLqRRLx0cl0hoJhjFWkFYowveq2Zn55dhM&index=68
        return{
            "type": "ir.actions.do_nothing"
        }
