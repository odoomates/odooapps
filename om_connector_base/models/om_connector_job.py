import json
import logging
import traceback
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.tools import SQL

from ..tools.exceptions import RetryableJobError

_logger = logging.getLogger(__name__)

JOB_METHOD_PREFIX = '_connector_job_'
DEFAULT_KEEP_DAYS = 30


class OmConnectorJob(models.Model):
    """ A piece of work for a connector: import an order, send a stock level, process a webhook…

    A job calls ``model_name.method_name(job)``. The method reads ``job.payload`` and
    ``job.backend``, and may return a record (linked to the job) or a short text (kept as the
    result). A job that fails is tried again later, a few minutes after each failure, up to
    ``max_attempts`` times. An error of the user (``UserError``, ``ValidationError``) fails the job
    at once: trying again would give the same error.
    """
    _name = 'om.connector.job'
    _description = 'Connector Job'
    _order = 'id desc'

    name = fields.Char(required=True)
    backend_model = fields.Char(string='Backend Model', required=True, index=True, readonly=True)
    backend_id = fields.Many2oneReference(string='Backend ID', model_field='backend_model', required=True,
                                          index=True, readonly=True)
    backend_name = fields.Char(string='Connection', compute='_compute_backend_name')
    company_id = fields.Many2one('res.company', required=True, index=True, readonly=True,
                                 default=lambda self: self.env.company)
    model_name = fields.Char(string='Model', required=True, readonly=True)
    method_name = fields.Char(string='Method', required=True, readonly=True)
    payload = fields.Json(readonly=True)
    payload_text = fields.Text(string='Data', compute='_compute_payload_text')
    dedupe_key = fields.Char(string='Key', readonly=True, index=True,
                             help="Two jobs of a connection never have the same key: a webhook sent twice, "
                                  "or the same order queued twice, makes one job.")
    state = fields.Selection([
        ('pending', 'To Do'),
        ('done', 'Done'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ], default='pending', required=True, index=True, readonly=True)
    priority = fields.Integer(default=10, help="Lower runs first.")
    eta = fields.Datetime(string='Run After', index=True, readonly=True)
    attempts = fields.Integer(readonly=True)
    max_attempts = fields.Integer(default=5)
    date_done = fields.Datetime(string='Done On', readonly=True)
    error = fields.Text(readonly=True)
    result = fields.Char(readonly=True)
    record_model = fields.Char(readonly=True)
    record_id = fields.Many2oneReference(string='Record ID', model_field='record_model', readonly=True)
    record_name = fields.Char(string='Record', compute='_compute_record_name')

    _dedupe_key_unique = models.Constraint(
        'unique (backend_model, backend_id, dedupe_key)', "A connection has one job per key.")
    _todo_index = models.Index('(priority, id) WHERE state = \'pending\'')

    @api.depends('backend_model', 'backend_id')
    def _compute_backend_name(self):
        for job in self:
            backend = job.backend
            job.backend_name = backend.sudo().display_name if backend else False

    @api.depends('record_model', 'record_id')
    def _compute_record_name(self):
        for job in self:
            record = job._get_record()
            job.record_name = record.sudo().display_name if record else False

    @api.depends('payload')
    def _compute_payload_text(self):
        for job in self:
            job.payload_text = json.dumps(job.payload, indent=2, ensure_ascii=False, default=str) \
                if job.payload is not None else False

    @property
    def backend(self):
        self.ensure_one()
        if not self.backend_model or self.backend_model not in self.env:
            return None
        return self.env[self.backend_model].browse(self.backend_id).exists()

    def _get_record(self):
        self.ensure_one()
        if not self.record_model or self.record_model not in self.env or not self.record_id:
            return None
        return self.env[self.record_model].browse(self.record_id).exists()

    @api.constrains('method_name')
    def _check_method_name(self):
        for job in self:
            if not job.method_name.startswith(JOB_METHOD_PREFIX):
                raise ValidationError(_("The method of a job starts with %(prefix)s.", prefix=JOB_METHOD_PREFIX))

    # ------------------------------------------------------------------
    # Queue
    # ------------------------------------------------------------------

    @api.model
    def _enqueue(self, backend, method_name, payload=None, *, model_name=None, name=None, dedupe_key=None,
                 priority=10, eta=None, max_attempts=5, company=None):
        """ Queue a job for ``backend``, or give the job of the same ``dedupe_key``.

        A pending job of the same key gets the new payload: the newest data of a record wins.
        A done, failed or cancelled job of the same key is put back to do with the new payload,
        unless ``payload`` is the same.
        """
        backend.ensure_one()
        Job = self.sudo()
        if dedupe_key:
            job = Job.search([('backend_model', '=', backend._name), ('backend_id', '=', backend.id),
                              ('dedupe_key', '=', dedupe_key)], limit=1)
            if job:
                if job.state == 'pending':
                    job.write({'payload': payload, 'priority': min(job.priority, priority)})
                elif job.payload != payload:
                    job.write({'payload': payload, 'state': 'pending', 'attempts': 0, 'error': False,
                               'eta': eta, 'date_done': False})
                    self._trigger_runner(eta)
                return job
        if company is None:
            company = backend.company_id if 'company_id' in backend._fields and backend.company_id \
                else self.env.company
        job = Job.create({
            'name': name or method_name.removeprefix(JOB_METHOD_PREFIX).replace('_', ' ').capitalize(),
            'backend_model': backend._name,
            'backend_id': backend.id,
            'company_id': company.id,
            'model_name': model_name or backend._name,
            'method_name': method_name,
            'payload': payload,
            'dedupe_key': dedupe_key,
            'priority': priority,
            'eta': eta,
            'max_attempts': max_attempts,
        })
        self._trigger_runner(eta)
        return job

    @api.model
    def _trigger_runner(self, eta=None):
        cron = self.env.ref('om_connector_base.ir_cron_om_connector_run_jobs', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger(eta)

    @api.model
    def _lock_next(self, limit, domain=None):
        """ The next jobs to run, locked for this transaction; jobs locked by another worker are
        skipped, so that two workers never run the same job. """
        domain = Domain.AND([
            [('state', '=', 'pending')],
            Domain.OR([[('eta', '=', False)], [('eta', '<=', fields.Datetime.now())]]),
            domain or [],
        ])
        query = self._search(domain, order='priority, id', limit=limit)
        self.env.cr.execute(SQL("%s FOR UPDATE SKIP LOCKED", query.select(SQL.identifier(self._table, 'id'))))
        return self.browse([row[0] for row in self.env.cr.fetchall()])

    @api.model
    def _cron_run_jobs(self, batch=20):
        """ Run the jobs to do, committing after each of them, until the time of the cron is over. """
        Cron = self.env['ir.cron']
        while True:
            jobs = self.sudo()._lock_next(batch)
            if not jobs:
                break
            for job in jobs:
                job._run()
                remaining = self.sudo().search_count([('state', '=', 'pending')])
                if not Cron._commit_progress(1, remaining=remaining):
                    return

    def _run(self):
        """ Run the job, in a savepoint: a failed job leaves no change but its own error. """
        self.ensure_one()
        if self.state != 'pending':
            return
        backend = self.backend
        if backend is None:
            self.write({'state': 'cancelled', 'error': _("The connection of this job has been deleted.")})
            return
        if self.model_name not in self.env or not self.method_name.startswith(JOB_METHOD_PREFIX):
            self.write({'state': 'failed', 'error': _("Unknown method %(model)s.%(method)s",
                                                      model=self.model_name, method=self.method_name)})
            return
        target = self.env[self.model_name].sudo().with_company(self.company_id)
        method = getattr(target, self.method_name, None)
        if method is None:
            self.write({'state': 'failed', 'error': _("Unknown method %(model)s.%(method)s",
                                                      model=self.model_name, method=self.method_name)})
            return
        attempts = self.attempts + 1
        try:
            with self.env.cr.savepoint():
                result = method(self.with_company(self.company_id))
        except RetryableJobError as e:
            self._failed(attempts, str(e), retry=True, delay=e.delay)
        except (UserError, ValidationError) as e:
            self._failed(attempts, str(e), retry=False)
        except (requests.ConnectionError, requests.Timeout) as e:
            self._failed(attempts, _("Network error: %(error)s", error=e), retry=True)
        except Exception:
            _logger.exception("Connector job %s (%s) failed", self.id, self.name)
            self._failed(attempts, traceback.format_exc(limit=8), retry=True)
        else:
            vals = {'state': 'done', 'attempts': attempts, 'date_done': fields.Datetime.now(), 'error': False}
            if isinstance(result, models.BaseModel) and len(result) == 1:
                vals.update(record_model=result._name, record_id=result.id)
            elif isinstance(result, str):
                vals['result'] = result[:250]
            self.write(vals)

    def _failed(self, attempts, error, retry, delay=None):
        vals = {'attempts': attempts, 'error': error}
        if retry and attempts < self.max_attempts:
            # 2, 4, 8, 16… minutes, at most 2 hours
            delay = delay if delay is not None else min(60 * 2 ** attempts, 7200)
            vals['eta'] = fields.Datetime.now() + timedelta(seconds=delay)
            self.write(vals)
            self._trigger_runner(vals['eta'])
        else:
            vals['state'] = 'failed'
            self.write(vals)
            backend = self.backend
            if backend is not None and hasattr(backend, '_connector_job_failed'):
                try:
                    with self.env.cr.savepoint():
                        backend._connector_job_failed(self)
                except Exception:
                    _logger.exception("Connector job %s: the failure could not be notified", self.id)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_retry(self):
        jobs = self.filtered(lambda j: j.state in ('failed', 'cancelled'))
        jobs.write({'state': 'pending', 'attempts': 0, 'eta': False, 'error': False})
        if jobs:
            self._trigger_runner()

    def action_cancel(self):
        self.filtered(lambda j: j.state in ('pending', 'failed')).write({'state': 'cancelled'})

    def action_run_now(self):
        for job in self.filtered(lambda j: j.state in ('pending', 'failed')):
            if job.state == 'failed':
                job.write({'state': 'pending', 'attempts': 0, 'error': False})
            job.eta = False
            job._run()

    def action_open_record(self):
        self.ensure_one()
        record = self._get_record()
        if not record:
            raise UserError(_("The record of this job does not exist anymore."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': record._name,
            'res_id': record.id,
            'view_mode': 'form',
        }

    @api.autovacuum
    def _gc_old_jobs(self):
        days = self.env['ir.config_parameter'].sudo().get_int('om_connector_base.job_keep_days') or DEFAULT_KEEP_DAYS
        limit_date = fields.Datetime.now() - timedelta(days=days)
        self.sudo().search([('state', 'in', ('done', 'cancelled')), ('write_date', '<', limit_date)],
                           limit=10000).unlink()
