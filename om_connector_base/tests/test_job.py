from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.om_connector_base.tools import RetryableJobError


@tagged('post_install', '-at_install')
class TestConnectorJob(TransactionCase):
    """ The queue, with a partner as the connection and handlers patched on res.partner. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Job = cls.env['om.connector.job']
        cls.backend = cls.env['res.partner'].create({'name': 'Test connection'})
        cls.Partner = type(cls.env['res.partner'])

    def _handler(self, func):
        return patch.object(self.Partner, '_connector_job_test', create=True, new=func)

    def _enqueue(self, **kwargs):
        return self.Job._enqueue(self.backend, '_connector_job_test', {'n': 1}, **kwargs)

    def test_dedupe_key(self):
        job = self._enqueue(dedupe_key='order:1')
        same = self.Job._enqueue(self.backend, '_connector_job_test', {'n': 2}, dedupe_key='order:1')
        self.assertEqual(job, same)
        self.assertEqual(job.payload, {'n': 2}, "a pending job gets the newest data")
        job.state = 'done'
        again = self.Job._enqueue(self.backend, '_connector_job_test', {'n': 2}, dedupe_key='order:1')
        self.assertEqual(again.state, 'done', "the same data does not run a done job again")
        again = self.Job._enqueue(self.backend, '_connector_job_test', {'n': 3}, dedupe_key='order:1')
        self.assertEqual(again.state, 'pending', "new data runs it again")

    def test_success_links_record(self):
        def handler(model, job):
            self.assertEqual(job.payload, {'n': 1})
            self.assertEqual(job.backend, self.backend)
            return model.env['res.partner'].create({'name': 'Made by job'})
        job = self._enqueue()
        with self._handler(handler):
            job._run()
        self.assertEqual(job.state, 'done')
        self.assertEqual(job.attempts, 1)
        self.assertEqual(job.record_name, 'Made by job')

    def test_user_error_fails_at_once(self):
        def handler(model, job):
            raise UserError("No such product")
        job = self._enqueue()
        with self._handler(handler):
            job._run()
        self.assertEqual(job.state, 'failed')
        self.assertIn('No such product', job.error)

    def test_error_retries_then_fails(self):
        def handler(model, job):
            model.env['res.partner'].create({'name': 'Rolled back'})
            raise ValueError("boom")
        job = self._enqueue(max_attempts=2)
        with self._handler(handler), self.assertLogs('odoo.addons.om_connector_base.models.om_connector_job', 'ERROR'):
            job._run()
            self.assertEqual(job.state, 'pending')
            self.assertEqual(job.attempts, 1)
            self.assertGreater(job.eta, fields.Datetime.now())
            self.assertFalse(self.env['res.partner'].search([('name', '=', 'Rolled back')]),
                             "the changes of a failed job are rolled back")
            with self.assertLogs('odoo.addons.om_connector_base.models.om_connector_job', 'ERROR'):
                job._run()
        self.assertEqual(job.state, 'failed')
        self.assertIn('boom', job.error)

    def test_retryable_error_delay(self):
        def handler(model, job):
            raise RetryableJobError("throttled", delay=30)
        job = self._enqueue()
        before = fields.Datetime.now()
        with self._handler(handler):
            job._run()
        self.assertEqual(job.state, 'pending')
        self.assertLessEqual(job.eta, before + timedelta(seconds=31))

    def test_lock_next_skips_future_jobs(self):
        later = self._enqueue(eta=fields.Datetime.now() + timedelta(hours=1))
        now = self._enqueue()
        urgent = self._enqueue(priority=1)
        jobs = self.Job._lock_next(10, [('backend_id', '=', self.backend.id)])
        self.assertEqual(jobs.ids, [urgent.id, now.id])
        self.assertNotIn(later, jobs)

    def test_retry_and_cancel(self):
        job = self._enqueue()
        job.action_cancel()
        self.assertEqual(job.state, 'cancelled')
        job.action_retry()
        self.assertEqual(job.state, 'pending')

    def test_method_prefix_is_required(self):
        with self.assertRaises(Exception):
            self.Job._enqueue(self.backend, 'unlink')
