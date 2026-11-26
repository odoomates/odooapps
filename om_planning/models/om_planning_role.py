from datetime import timedelta
from random import randint

from odoo import api, fields, models


class OmPlanningRole(models.Model):
    _name = 'om.planning.role'
    _description = "Planning Role"
    _order = 'sequence, name'

    def _default_color(self):
        return randint(1, 11)

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(default=_default_color)
    resource_ids = fields.Many2many(
        'resource.resource', 'om_planning_role_resource_rel', 'role_id', 'resource_id',
        string="Resources")
    resource_count = fields.Integer(compute='_compute_resource_count', string="Resource Count")
    template_id = fields.Many2one(
        'om.planning.template', string="Default Template",
        help="Hours proposed for the new slots of this role.")
    allow_overlap = fields.Boolean(
        string="Allow Overlap",
        help="Slots of this role may overlap other slots of the same resource without a conflict.")
    slot_properties_definition = fields.PropertiesDefinition("Slot Properties")
    company_id = fields.Many2one('res.company', string="Company")
    slot_count = fields.Integer(compute='_compute_slot_count', string="Slot Count")

    @api.depends('resource_ids')
    def _compute_resource_count(self):
        for role in self:
            role.resource_count = len(role.resource_ids)

    def _compute_slot_count(self):
        counts = dict(self.env['om.planning.slot']._read_group(
            [('role_id', 'in', self.ids)], ['role_id'], ['__count']))
        for role in self:
            role.slot_count = counts.get(role, 0)

    def action_view_slots(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_planning.action_om_planning_slot')
        action['domain'] = [('role_id', '=', self.id)]
        action['context'] = {'default_role_id': self.id, 'search_default_group_role': 0}
        return action

    def _planning_find_free(self, start, stop, qty=1):
        """ Resources of the role free on the whole period ``start`` - ``stop``.

        A resource is free when the period is inside its working time (leaves removed) and
        the slots already booked leave room for one more (``planning_capacity`` for pools).

        :param datetime start: start (naive UTC or aware)
        :param datetime stop: end (naive UTC or aware)
        :param int qty: number of resources wanted
        :return: ``resource.resource`` recordset, at most ``qty`` records, least loaded first
        """
        self.ensure_one()
        resources = self.resource_ids.filtered('active')
        if not resources:
            return resources
        free = resources._planning_free_intervals(start, stop)
        start_utc, stop_utc = resources._planning_utc(start), resources._planning_utc(stop)
        # a minute of tolerance on the bounds of the working periods
        tolerance = timedelta(minutes=1)
        candidates = resources.filtered(lambda r: any(
            s <= start_utc + tolerance and e >= stop_utc - tolerance for s, e, _recs in free[r.id]))
        load = candidates._planning_booked_hours(start_utc - timedelta(days=7), stop_utc + timedelta(days=7))
        return candidates.sorted(lambda r: (load.get(r.id, 0.0), r.name))[:qty]
