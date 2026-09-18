# Copyright © Jenrax SRL - www.jenrax.com
from odoo import api, fields, models


class TaskChecklist(models.Model):
    _name = "task.checklist"
    _description = "Checklist for Task"
    _order = "sequence, id"

    name = fields.Char(required=True)
    description = fields.Char()
    project_id = fields.Many2one(
        "project.project",
        string="Project",
        ondelete="cascade",
        help="Leave empty for a global checklist (fallback for projects with no own checklists).",
    )
    sequence = fields.Integer(default=10)


class ProjectTask(models.Model):
    _inherit = "project.task"

    task_checklist = fields.Many2many(
        "task.checklist",
        string="Check List",
    )
    available_checklist_ids = fields.Many2many(
        "task.checklist",
        relation="project_task_available_checklist_rel",
        compute="_compute_available_checklist_ids",
    )
    checklist_progress = fields.Float(
        compute="_compute_checklist_progress",
        string="Progress",
    )

    def _project_checklist_domain(self, task):
        """Return the domain for checklists: project-specific items, or globals as fallback."""
        has_project = self.env["task.checklist"].search_count(
            [("project_id", "=", task.project_id.id)]
        )
        if has_project:
            return [("project_id", "=", task.project_id.id)]
        return [("project_id", "=", False)]

    @api.depends("project_id")
    def _compute_available_checklist_ids(self):
        for task in self:
            task.available_checklist_ids = self.env["task.checklist"].search(
                self._project_checklist_domain(task)
            )

    @api.depends("task_checklist", "project_id")
    def _compute_checklist_progress(self):
        for task in self:
            total = self.env["task.checklist"].search_count(
                self._project_checklist_domain(task)
            )
            task.checklist_progress = (
                len(task.task_checklist) * 100.0 / total if total else 0.0
            )
