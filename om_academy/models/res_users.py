from datetime import timedelta

from odoo import fields, models

DAYS_KEPT = 120


class ResUsers(models.Model):
    _inherit = 'res.users'

    academy_welcomed = fields.Boolean(help="The learner went through the welcome guide of the Academy.")
    academy_warmup = fields.Json(help="The warm-up of the Academy: answers, tasks done, and what was there at the start.")
    academy_bugs = fields.Json(help="The bug hunt of the Academy: the bugs found, and the tries.")
    academy_days = fields.Json(help="The days the learner learned in the Academy, for their streak.")

    def _academy_active(self):
        """ The learner learned today: a step, a question, a bug. """
        today = fields.Date.to_string(fields.Date.context_today(self))
        days = list(self.academy_days or [])
        if today not in days:
            self.sudo().academy_days = (days + [today])[-DAYS_KEPT:]

    def _academy_streak(self):
        """ {'current', 'best', 'today'}: the days in a row, up to today or yesterday. """
        days = sorted({fields.Date.to_date(day) for day in self.academy_days or []})
        today = fields.Date.context_today(self)
        best = run = 0
        previous = None
        for day in days:
            run = run + 1 if previous and day - previous == timedelta(days=1) else 1
            best = max(best, run)
            previous = day
        current = run if previous and today - previous <= timedelta(days=1) else 0
        return {'current': current, 'best': best, 'today': bool(previous and previous == today)}
