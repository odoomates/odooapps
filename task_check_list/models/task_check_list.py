# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ProjectTask(models.Model):
    _inherit = 'project.task'

    @api.depends('task_checklist')
    def checklist_progress(self):
        total_len = self.env['task.checklist'].search_count([])
        for rec in self:
            if total_len != 0:
                check_list_len = len(rec.task_checklist)
                rec.checklist_progress = (check_list_len * 100) / total_len
            else:
                rec.checklist_progress = 0

    task_checklist = fields.Many2many('task.checklist', string='Check List')
    checklist_progress = fields.Float(compute=checklist_progress, string='Progress', store=True,
                                      default=0.0)
    max_rate = fields.Integer(string='Maximum rate', default=100)


class TaskChecklist(models.Model):
    _name = 'task.checklist'
    _description = 'Checklist for the task'

    name = fields.Char(string='Name', required=True)
    description = fields.Char(string='Description')
