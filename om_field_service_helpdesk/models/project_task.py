from odoo import fields, models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    helpdesk_ticket_id = fields.Many2one(
        'om.helpdesk.ticket', string="Helpdesk Ticket", index='btree_not_null', copy=False, tracking=True,
        help="Ticket this job was made from: told when the job is done.")

    def _fs_on_done(self):
        res = super()._fs_on_done()
        for job in self.filtered('helpdesk_ticket_id'):
            job.helpdesk_ticket_id.sudo()._fs_job_done(job)
        return res

    def action_fs_view_ticket(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'om.helpdesk.ticket',
            'res_id': self.helpdesk_ticket_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }
