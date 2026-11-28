# What must not happen during a simulation: what leaves the database (an
# email sent cannot be taken back), what replaces the registry it lives in
# (installing or upgrading a module), and the scheduled jobs that would work on
# data that is not there for them.
import logging

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.base.models.ir_cron import IrCron

from . import simulation

_logger = logging.getLogger(__name__)


class IrMailServer(models.Model):
    _inherit = 'ir.mail_server'

    @api.model
    def send_email(self, message, *args, **kwargs):
        if simulation.current(self.env.cr.dbname):
            _logger.info("Simulation: email %r not sent", message['Subject'])
            return message['Message-Id'] or 'flow-simulation'
        return super().send_email(message, *args, **kwargs)


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def _button_immediate_function(self, function):
        if simulation.current(self.env.cr.dbname):
            raise UserError(_("Keep or discard the simulation before installing, upgrading or removing modules."))
        return super()._button_immediate_function(function)


_process_jobs = IrCron._process_jobs


def _process_jobs_unless_simulated(db_name):
    if simulation.current(db_name):
        return
    _process_jobs(db_name)


IrCron._process_jobs = staticmethod(_process_jobs_unless_simulated)
