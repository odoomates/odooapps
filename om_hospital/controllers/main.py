from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale


class AppointmentController(http.Controller):

    @http.route('/om_hospital/appointments', auth='user', type='json')
    def appointment_banner(self):
        return {
            'html': """
                    <div>
                        <link>
                        <center><h1><font color="red">Subscribe the channel.......!</font></h1></center>
                        <center>
                        <p><font color="blue"><a href="https://www.youtube.com/channel/UCVKlUZP7HAhdQgs-9iTJklQ/videos">
                            Get Notified Regarding All The Odoo Updates!</a></p>
                            </font></div></center> """
                                }


class WebsiteSaleInherit(WebsiteSale):

    @http.route([
        '''/shop''',
        '''/shop/page/<int:page>''',
        '''/shop/category/<model("product.public.category", "[('website_id', 'in', (False, current_website_id))]"):category>''',
        '''/shop/category/<model("product.public.category", "[('website_id', 'in', (False, current_website_id))]"):category>/page/<int:page>'''
    ], type='http', auth="public", website=True)
    def shop(self, page=0, category=None, search='', ppg=False, **post):
        res = super(WebsiteSaleInherit, self).shop(page=0, category=None, search='', ppg=False, **post)
        print("Inherited Odoo Mates ....", res)
        return res


class Hospital(http.Controller):

    @http.route('/patient_webform', type="http", auth="public", website=True)
    def patient_webform(self, **kw):
        print("Execution Here.........................")
        doctor_rec = request.env['hospital.doctor'].sudo().search([])
        print("doctor_rec...", doctor_rec)
        return http.request.render('om_hospital.create_patient', {'patient_name': 'Odoo Mates Test 123',
                                                                  'doctor_rec': doctor_rec})

    @http.route('/create/webpatient', type="http", auth="public", website=True)
    def create_webpatient(self, **kw):
        print("Data Received.....", kw)
        request.env['hospital.patient'].sudo().create(kw)
        # doctor_val = {
        #     'name': kw.get('patient_name')
        # }
        # request.env['hospital.doctor'].sudo().create(doctor_val)
        return request.render("om_hospital.patient_thanks", {})







    # @http.route('/patient_webform', website=True, auth='user')
    # def patient_webform(self):
    #     return request.render("om_hospital.patient_webform", {})
    #
    # # Check and insert values from the form on the model <model>
    # @http.route(['/create_web_patient'], type='http', auth="public", website=True)
    # def patient_contact_create(self, **kwargs):
    #     print("ccccccccccccc")
    #     request.env['hospital.patient'].sudo().create(kwargs)
    #     return request.render("om_hospital.patient_thanks", {})



    # Sample Controller Created
    @http.route('/hospital/patient/', website=True, auth='user')
    def hospital_patient(self, **kw):
        # return "Thanks for watching"
        patients = request.env['hospital.patient'].sudo().search([])
        return request.render("om_hospital.patients_page", {
            'patients': patients
        })

    # Sample Controller Created
    @http.route('/update_patient', type='json', auth='user')
    def update_patient(self, **rec):
        if request.jsonrequest:
            if rec['id']:
                print("rec...", rec)
                patient = request.env['hospital.patient'].sudo().search([('id', '=', rec['id'])])
                if patient:
                    patient.sudo().write(rec)
                args = {'success': True, 'message': 'Patient Updated'}
        return args

    @http.route('/create_patient', type='json', auth='user')
    def create_patient(self, **rec):
        if request.jsonrequest:
            print("rec", rec)
            if rec['name']:
                vals = {
                    'patient_name': rec['name'],
                    'email_id': rec['email_id']
                }
                new_patient = request.env['hospital.patient'].sudo().create(vals)
                print("New Patient Is", new_patient)
                args = {'success': True, 'message': 'Success', 'id': new_patient.id}
        return args

    @http.route('/get_patients', type='json', auth='user')
    def get_patients(self):
        print("Yes here entered")
        patients_rec = request.env['hospital.patient'].search([])
        patients = []
        for rec in patients_rec:
            vals = {
                'id': rec.id,
                'name': rec.patient_name,
                'sequence': rec.name_seq,
            }
            patients.append(vals)
        print("Patient List--->", patients)
        data = {'status': 200, 'response': patients, 'message': 'Done All Patients Returned'}
        return data
