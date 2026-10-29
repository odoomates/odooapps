from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestHospital(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.patient = cls.env['hospital.patient'].create({'name': 'Anna', 'date_of_birth': '2010-01-01'})
        cls.doctor = cls.env['hospital.doctor'].create({'doctor_name': 'Dr House'})

    def appointment(self, **values):
        return self.env['hospital.appointment'].create(dict({'patient_id': self.patient.id, 'doctor_id': self.doctor.id}, **values))

    def test_sequences_and_display_name(self):
        self.assertTrue(self.patient.reference.startswith('PT'))
        self.assertEqual(self.patient.display_name, '[%s] Anna' % self.patient.reference)
        patients = self.env['hospital.patient'].create([{'name': 'Bob'}, {'name': 'Carla'}])
        self.assertEqual(len(set(patients.mapped('reference'))), 2, "create works in batch")
        found = self.env['hospital.patient'].name_search(self.patient.reference)
        self.assertEqual(found[0][0], self.patient.id, "a patient is found by reference too")

    def test_age_and_constraints(self):
        self.assertGreater(self.patient.age, 10)
        with self.assertRaises(ValidationError):
            self.env['hospital.patient'].create({'name': 'Future', 'date_of_birth': '2999-01-01'})
        with self.assertRaises(ValidationError):
            self.appointment(duration=0)

    def test_status_and_delete(self):
        appointment = self.appointment()
        self.assertTrue(appointment.name.startswith('AP'))
        self.assertEqual(appointment.age, self.patient.age)
        appointment.action_confirm()
        self.assertEqual(appointment.state, 'confirm')
        appointment.action_done()
        with self.assertRaises(UserError):
            appointment.unlink()
        self.assertEqual(self.patient.appointment_count, 1)
        self.assertEqual(self.doctor.appointment_count, 1)

    def test_cancellation_limit(self):
        self.env['ir.config_parameter'].set_param('om_hospital.cancel_days', 2)
        with self.assertRaises(UserError):
            self.appointment().action_cancel()
        self.env['ir.config_parameter'].set_param('om_hospital.cancel_days', 0)
        appointment = self.appointment()
        appointment.action_cancel()
        self.assertEqual(appointment.state, 'cancel')

    def test_wizards(self):
        wizard = self.env['create.appointment.wizard'].with_context(
            active_model='hospital.patient', active_id=self.patient.id).create({'doctor_id': self.doctor.id})
        self.assertEqual(wizard.patient_id, self.patient)
        action = wizard.action_create_appointment()
        self.assertEqual(self.env['hospital.appointment'].browse(action['res_id']).patient_id, self.patient)
        search = self.env['search.appointment.wizard'].create({'patient_id': self.patient.id})
        self.assertEqual(search.action_search_ref()['domain'], [('patient_id', '=', self.patient.id)])

    def test_report(self):
        self.appointment()
        html = self.env['ir.actions.report']._render_qweb_html('om_hospital.action_report_patient_card', self.patient.ids)[0]
        self.assertIn(b'Patient Card', html)

    def test_courses(self):
        channels = self.env['slide.channel'].search([('id', 'in', [
            self.env.ref('om_hospital.slide_channel_course_%d' % number).id for number in range(1, 7)])])
        self.assertEqual(len(channels), 6)
        slides = channels.slide_ids
        videos = slides.filtered(lambda slide: slide.slide_category == 'video')
        self.assertGreater(len(videos), 100)
        self.assertTrue(all(video.youtube_id for video in videos), "every video is a YouTube video")
        quizzes = slides.filtered(lambda slide: slide.slide_category == 'quiz')
        self.assertTrue(quizzes and all(len(quiz.question_ids) >= 3 for quiz in quizzes))
        self.assertTrue(all(question.answer_ids.filtered('is_correct') for question in quizzes.question_ids))
        self.assertTrue(all(channel.is_published for channel in channels))
