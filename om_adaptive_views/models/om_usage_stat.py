import json
from datetime import timedelta

from odoo import api, fields, models
from odoo.tools import SQL

# what the web client reports, and on which kind of screen
EVENTS = {
    'save': 'form',         # a form was saved with changes
    'edit': 'form',         # a field was changed in that save
    'visit': 'search',      # an action was opened on its records
    'filter': 'search',     # a filter or group-by was switched on by hand
    'column_on': 'list',    # an optional column was switched on
    'column_off': 'list',   # an optional column was switched off
    'menu': 'menu',         # a menu was opened
}
MAX_EVENTS = 500
OWN_MODELS = ('om.adapt.', 'om.usage.')
MAX_COUNT = 1000
HISTORY_WEEKS = 13


def monday(day):
    return day - timedelta(days=day.weekday())


class OmUsageStat(models.Model):
    """ How often each part of a screen is used, counted per company and per week.

    Only counts are kept: which field was changed, never what was typed in it.
    """
    _name = 'om.usage.stat'
    _description = 'Screen usage'
    _order = 'week desc, count desc'
    _log_access = False

    company_id = fields.Many2one('res.company', required=True, index=True, ondelete='cascade')
    model = fields.Char(required=True, index=True)
    model_label = fields.Char(string='Model name', compute='_compute_model_label')
    view_type = fields.Selection(
        [('form', 'Form'), ('list', 'List'), ('search', 'Search'), ('menu', 'Menu')], required=True)
    view_id = fields.Integer(string='View', default=0, required=True)
    action_id = fields.Integer(string='Action', default=0, required=True)
    role_id = fields.Integer(
        string='Role', default=0, required=True,
        help="The group the uses were counted for, when roles are learnt separately; 0 for everyone.")
    element = fields.Char(required=True, default='', help="The field, filter, column or menu used.")
    event = fields.Selection([
        ('save', 'Saved'),
        ('edit', 'Field changed'),
        ('visit', 'Opened'),
        ('filter', 'Filter applied'),
        ('column_on', 'Column shown'),
        ('column_off', 'Column hidden'),
        ('menu', 'Menu opened'),
    ], required=True)
    week = fields.Date(required=True, help="The Monday of the week the uses were counted in.")
    count = fields.Integer(required=True, default=0)

    _om_usage_uniq = models.UniqueIndex(
        "(company_id, model, view_type, view_id, action_id, role_id, element, event, week)")

    @api.depends('model')
    def _compute_model_label(self):
        labels = {model.model: model.name for model in self.env['ir.model'].sudo().search(
            [('model', 'in', list(set(self.mapped('model'))))])}
        for stat in self:
            stat.model_label = labels.get(stat.model, stat.model)

    @api.model
    def _om_user_role(self, user):
        """ The role a user is counted for: the first role of the company they belong to. """
        roles = self.env.company.sudo().om_adapt_role_ids.sorted('id')
        groups = user.sudo().all_group_ids
        return next((role for role in roles if role in groups), self.env['res.groups'])

    @api.model
    def _om_role(self):
        """ The role the current user's uses are counted for: 0 for everyone. """
        return self._om_user_role(self.env.user).id or 0

    @api.model
    def _om_record(self, events):
        """ Add the counts reported by a web client to this week's totals.

        Anything that does not look like a report of ours is dropped: the route is open
        to every user, and only counts of real models and short names are kept.
        """
        week = monday(fields.Date.context_today(self))
        company = self.env.company.id
        role = self._om_role()
        totals = {}
        for event in (events or [])[:MAX_EVENTS]:
            if not isinstance(event, dict):
                continue
            kind = event.get('event')
            model = event.get('model')
            element = event.get('element') or ''
            count = event.get('count')
            if kind not in EVENTS or model not in self.env or not isinstance(element, str):
                continue
            if model.startswith(OWN_MODELS):
                continue  # the screens of this module are not adapted to themselves
            if not isinstance(count, int) or not 0 < count <= MAX_COUNT or len(element) > 128:
                continue
            view_id = event.get('view_id') if isinstance(event.get('view_id'), int) else 0
            action_id = event.get('action_id') if isinstance(event.get('action_id'), int) else 0
            key = (model, EVENTS[kind], view_id, action_id, role, element, kind)
            totals[key] = totals.get(key, 0) + count
        if not totals or self._om_read_only():
            return 0
        # one row per key: an upsert may not touch the same row twice
        rows = [SQL("(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", company, *key, week, count)
                for key, count in totals.items()]
        # a SQL upsert: every page of every user reports here, so it must stay cheap
        self.env.cr.execute(SQL(
            """INSERT INTO om_usage_stat
                   (company_id, model, view_type, view_id, action_id, role_id, element, event, week, count)
               VALUES %s
               ON CONFLICT (company_id, model, view_type, view_id, action_id, role_id, element, event, week)
               DO UPDATE SET count = om_usage_stat.count + EXCLUDED.count""",
            SQL(", ").join(rows),
        ))
        self._om_after_record(events)
        return len(rows)

    @api.model
    def _om_read_only(self):
        """ Whether nothing may be written now, as when someone previews another user's
        screens: the uses seen then are not counted. """
        if self.env.cr.readonly:
            return True
        self.env.cr.execute("SHOW transaction_read_only")
        return self.env.cr.fetchone()[0] == 'on'

    def _om_after_record(self, events):
        """ The visits, filters and menus of each person, for their own defaults. """
        self.env['om.usage.user.stat']._om_record_user(events)

    @api.model
    def _om_totals(self, company, since, view_type, events, role=None):
        """ Sums per screen and element since a date: {(model, view_id, action_id, element, event): count}.

        ``role`` limits the sums to one role; by default every role is added up.
        """
        role_clause = SQL("") if role is None else SQL("AND role_id = %s", role)
        self.env.cr.execute(SQL(
            """SELECT model, view_id, action_id, element, event, SUM(count)
                 FROM om_usage_stat
                WHERE company_id = %s AND week >= %s AND view_type = %s AND event IN %s %s
             GROUP BY model, view_id, action_id, element, event""",
            company.id, since, view_type, tuple(events), role_clause,
        ))
        return {tuple(row[:5]): row[5] for row in self.env.cr.fetchall()}

    @api.model
    def _om_weekly(self, company, view_type, events, role=None):
        """ The weekly counts of the last weeks, oldest first, and the last week with a use.

        Returns {(model, view_id, action_id, element): (json list, last used date or False)}.
        """
        this_week = monday(fields.Date.context_today(self))
        weeks = [this_week - timedelta(weeks=n) for n in range(HISTORY_WEEKS - 1, -1, -1)]
        role_clause = SQL("") if role is None else SQL("AND role_id = %s", role)
        self.env.cr.execute(SQL(
            """SELECT model, view_id, action_id, element, week, SUM(count)
                 FROM om_usage_stat
                WHERE company_id = %s AND week >= %s AND view_type = %s AND event IN %s %s
             GROUP BY model, view_id, action_id, element, week""",
            company.id, weeks[0], view_type, tuple(events), role_clause,
        ))
        series = {}
        for model, view_id, action_id, element, week, count in self.env.cr.fetchall():
            series.setdefault((model, view_id, action_id, element), {})[week] = count
        result = {}
        for key, by_week in series.items():
            used = [week for week, count in by_week.items() if count]
            result[key] = (json.dumps([by_week.get(week, 0) for week in weeks]), max(used) if used else False)
        return result

    @api.model
    def _om_no_history(self):
        return json.dumps([0] * HISTORY_WEEKS)

    @api.model
    def _om_purge(self):
        """ Counts older than the analysis window are of no further use. """
        days = self.env['om.adapt.rule']._om_param('days')
        limit = monday(fields.Date.context_today(self)) - timedelta(days=days + 7)
        self.env.cr.execute(SQL("DELETE FROM om_usage_stat WHERE week < %s", limit))
        self.env['om.usage.user.stat']._om_purge()
        return True


class OmUsageUserStat(models.Model):
    """ The actions each person opens, the filters they apply and the menus they open, per week.

    Kept apart from the shared counts: what one person uses becomes their own default filter
    and their own menu order, never anyone else's.
    """
    _name = 'om.usage.user.stat'
    _description = 'Personal usage'
    _log_access = False

    company_id = fields.Many2one('res.company', required=True, index=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', required=True, index=True, ondelete='cascade')
    model = fields.Char(required=True)
    action_id = fields.Integer(required=True, default=0)
    element = fields.Char(required=True, default='')
    event = fields.Selection([('visit', 'Opened'), ('filter', 'Filter applied'), ('menu', 'Menu opened')],
                             required=True)
    week = fields.Date(required=True)
    count = fields.Integer(required=True, default=0)

    _om_user_usage_uniq = models.UniqueIndex("(company_id, user_id, model, action_id, element, event, week)")

    @api.model
    def _om_record_user(self, events):
        week = monday(fields.Date.context_today(self))
        totals = {}
        for event in (events or [])[:MAX_EVENTS]:
            if not isinstance(event, dict) or event.get('event') not in ('visit', 'filter', 'menu'):
                continue
            model, element, count = event.get('model'), event.get('element') or '', event.get('count')
            action_id = event.get('action_id') if isinstance(event.get('action_id'), int) else 0
            if model not in self.env or not isinstance(element, str) or len(element) > 128:
                continue
            if not isinstance(count, int) or not 0 < count <= MAX_COUNT:
                continue
            key = (model, action_id, element, event['event'])
            totals[key] = totals.get(key, 0) + count
        if not totals:
            return
        rows = [SQL("(%s, %s, %s, %s, %s, %s, %s, %s)", self.env.company.id, self.env.uid, *key, week, count)
                for key, count in totals.items()]
        self.env.cr.execute(SQL(
            """INSERT INTO om_usage_user_stat (company_id, user_id, model, action_id, element, event, week, count)
               VALUES %s
               ON CONFLICT (company_id, user_id, model, action_id, element, event, week)
               DO UPDATE SET count = om_usage_user_stat.count + EXCLUDED.count""",
            SQL(", ").join(rows),
        ))

    @api.model
    def _om_user_totals(self, company, since, events):
        """ {(user_id, model, action_id, element, event): count} since a date. """
        self.env.cr.execute(SQL(
            """SELECT user_id, model, action_id, element, event, SUM(count)
                 FROM om_usage_user_stat WHERE company_id = %s AND week >= %s AND event IN %s
             GROUP BY user_id, model, action_id, element, event""",
            company.id, since, tuple(events),
        ))
        return {tuple(row[:5]): row[5] for row in self.env.cr.fetchall()}

    @api.model
    def _om_purge(self):
        days = self.env['om.adapt.rule']._om_param('days')
        limit = monday(fields.Date.context_today(self)) - timedelta(days=days + 7)
        self.env.cr.execute(SQL("DELETE FROM om_usage_user_stat WHERE week < %s", limit))
        return True
