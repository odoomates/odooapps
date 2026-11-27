import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, MissingError, UserError

_logger = logging.getLogger(__name__)

BATCH = 20


class OmAiFieldJob(models.Model):
    """A record waiting for its fields to be filled by the AI. Jobs are run by
    a triggered scheduled action so that saving a record never waits for the AI."""
    _name = 'om.ai.field.job'
    _description = 'AI Field Queue'
    _order = 'id'

    action_id = fields.Many2one('ir.actions.server', string='Server Action', required=True, ondelete='cascade',
                                index=True)
    res_model = fields.Char(string='Model', required=True)
    res_id = fields.Integer(string='Record ID', required=True)
    record_name = fields.Char(string='Record', compute='_compute_record_name')
    user_id = fields.Many2one('res.users', string='User', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', string='Company', required=True, ondelete='cascade')
    state = fields.Selection([('pending', 'Pending'), ('done', 'Done'), ('failed', 'Failed')],
                             default='pending', required=True, index=True)
    error = fields.Text()
    date_done = fields.Datetime(string='Done On')

    def _compute_record_name(self):
        for job in self:
            record = self.env[job.res_model].browse(job.res_id).exists() if job.res_model in self.env else None
            job.record_name = record.display_name if record else '%s,%s' % (job.res_model, job.res_id)

    @api.model
    def _enqueue(self, action, records):
        """Queue ``records`` for ``action`` unless they are already waiting."""
        if not records:
            return self
        pending = set(self.sudo().search([
            ('action_id', '=', action.id), ('res_model', '=', records._name),
            ('res_id', 'in', records.ids), ('state', '=', 'pending'),
        ]).mapped('res_id'))
        jobs = self.sudo().create([{
            'action_id': action.id,
            'res_model': records._name,
            'res_id': record_id,
            'user_id': self.env.user.id,
            'company_id': self.env.company.id,
        } for record_id in records.ids if record_id not in pending])
        if jobs:
            self.env.ref('om_ai_fields.ir_cron_om_ai_field_jobs').sudo()._trigger()
        return jobs

    def _cron_process(self):
        jobs = self.search([('state', '=', 'pending')], limit=BATCH)
        Cron = self.env['ir.cron']
        Cron._commit_progress(remaining=len(jobs))
        for job in jobs:
            job._process()
            if not Cron._commit_progress(1):
                break
        if self.search_count([('state', '=', 'pending')], limit=1):
            self.env.ref('om_ai_fields.ir_cron_om_ai_field_jobs')._trigger()
        else:
            self.search([('state', '=', 'done'),
                         ('date_done', '<', fields.Datetime.now() - timedelta(days=7))]).unlink()

    def _process(self):
        self.ensure_one()
        user = self.user_id
        env = self.with_user(user).with_context(
            allowed_company_ids=(self.company_id | user.company_ids).ids, lang=user.lang, tz=user.tz,
            om_ai_fields_running=True,
        ).with_company(self.company_id).env
        try:
            with self.env.cr.savepoint():
                record = env[self.res_model].browse(self.res_id).exists()
                if not record:
                    raise MissingError(self.env._('The record no longer exists.'))
                result = self.action_id.with_env(env)._om_ai_fill_now(record)
            if result['errors']:
                self.write({'state': 'failed', 'error': '\n'.join(result['errors']),
                            'date_done': fields.Datetime.now()})
            else:
                self.write({'state': 'done', 'error': False, 'date_done': fields.Datetime.now()})
        except (UserError, AccessError, MissingError) as error:
            self.write({'state': 'failed', 'error': str(error.args[0] if error.args else error),
                        'date_done': fields.Datetime.now()})
        except Exception as error:  # noqa: BLE001 - one failing record must not stop the queue
            _logger.exception('AI field job %s failed', self.id)
            self.write({'state': 'failed', 'error': repr(error), 'date_done': fields.Datetime.now()})

    def action_retry(self):
        self.write({'state': 'pending', 'error': False})
        self.env.ref('om_ai_fields.ir_cron_om_ai_field_jobs').sudo()._trigger()
        return True

    def action_open_record(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }
