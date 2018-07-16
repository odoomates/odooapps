# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ProjectTask(models.Model):
    _inherit = 'project.task'

    @api.depends('task_checklist')
    def checklist_progress(self):
        """:return the value for the check list progress"""
        for rec in self:
            total_len = self.env['task.checklist'].search_count([])
            check_list_len = len(rec.task_checklist)
            if total_len != 0:
                rec.checklist_progress = (check_list_len*100) / total_len

    task_checklist = fields.Many2many('task.checklist', string='Check List')
    checklist_progress = fields.Float(compute=checklist_progress, string='Progress', store=True, recompute=True,
                                      default=0.0)
    max_rate = fields.Integer(string='Maximum rate', default=100)


class TaskChecklist(models.Model):
    _name = 'task.checklist'
    _description = 'Checklist for the task'

    name = fields.Char(string='Name', required=True)
    description = fields.Char(string='Description')
