import logging
from datetime import timedelta

import psycopg2

from odoo import fields, models
from odoo.tools import SQL

_logger = logging.getLogger(__name__)


class OmAiWhatsappJob(models.Model):
    """ A customer message waiting for the assistant. The webhook of the
    provider only makes the job; a scheduled action answers it, so receiving
    never waits for the AI. """
    _name = 'om.ai.whatsapp.job'
    _description = 'WhatsApp AI Job'
    _order = 'id'

    conversation_id = fields.Many2one('om.ai.whatsapp.conversation', required=True, ondelete='cascade', index=True)
    message_id = fields.Many2one('mail.message', ondelete='cascade', index=True)
    state = fields.Selection([('pending', 'Pending'), ('done', 'Done'), ('failed', 'Failed')],
                             default='pending', required=True, index=True)
    replied = fields.Boolean(readonly=True)
    error = fields.Text(readonly=True)

    def _cron_process(self):
        jobs = self.search([('state', '=', 'pending')], limit=20)
        Cron = self.env['ir.cron']
        Cron._commit_progress(remaining=len(jobs))
        for job in jobs:
            job._process()
            if not Cron._commit_progress(1):
                break
        if self.search_count([('state', '=', 'pending')], limit=1):
            self.env.ref('om_ai_whatsapp.ir_cron_om_ai_whatsapp_jobs')._trigger()
        else:
            self.search([('state', '!=', 'pending'),
                         ('create_date', '<', fields.Datetime.now() - timedelta(days=30))]).unlink()

    def _process(self):
        self.ensure_one()
        if self.state != 'pending':
            return
        # another worker answering it already: skip
        self.env.cr.execute(SQL("SELECT id FROM %s WHERE id = %s AND state = 'pending' FOR UPDATE SKIP LOCKED",
                                SQL.identifier(self._table), self.id))
        if not self.env.cr.fetchone():
            return
        conversation = self.conversation_id
        # messages sent one after the other get one answer, to the last one
        if self.search_count([('conversation_id', '=', conversation.id), ('state', '=', 'pending'),
                              ('id', '>', self.id)], limit=1):
            self.state = 'done'
            return
        try:
            with self.env.cr.savepoint():
                replied = conversation._om_ai_handle(self.message_id)
            self.write({'state': 'done', 'replied': bool(replied)})
        except psycopg2.OperationalError:
            # a concurrent update: the scheduled action runs it again
            raise
        except Exception as error:  # noqa: BLE001 - one failing message never stops the others
            _logger.exception("WhatsApp assistant failed on message %s", self.message_id.id)
            self.write({'state': 'failed', 'error': repr(error)})
            try:
                with self.env.cr.savepoint():
                    conversation._om_ai_hand_over(
                        self.env._('the assistant met an error'),
                        message=self.env._("Thank you for your message! A colleague will answer you here shortly."))
            except Exception:  # noqa: BLE001
                _logger.exception("WhatsApp assistant could not hand over %s", conversation.number)
