from odoo import api, fields, models


class OmPlanningSource(models.AbstractModel):
    """ Mixin for documents that book planning time (orders, tasks, tickets, rentals...).

    The slots of a document are the slots whose ``source_ref`` points to it. Override
    :meth:`_planning_hours_to_plan` and :meth:`_planning_slot_values` in the model.
    """
    _name = 'om.planning.source'
    _description = "Planning Source"

    planning_slot_ids = fields.Many2many(
        'om.planning.slot', compute='_compute_planning_slot_ids', string="Planning Slots")
    planning_slot_count = fields.Integer(compute='_compute_planning_slot_ids', string="Slot Count")
    planning_hours_to_plan = fields.Float(compute='_compute_planning_hours', string="Hours to Plan")
    planning_hours_planned = fields.Float(compute='_compute_planning_hours', string="Hours Planned")
    planning_status = fields.Selection([
        ('none', 'Not Planned'),
        ('partial', 'Partially Planned'),
        ('planned', 'Planned'),
    ], compute='_compute_planning_hours', string="Planning Status")

    def _planning_source_refs(self):
        return [f'{record._name},{record.id}' for record in self if record.id]

    def _compute_planning_slot_ids(self):
        Slot = self.env['om.planning.slot']
        slots = Slot.search([('source_ref', 'in', self._planning_source_refs())]) if self.ids else Slot
        per_ref = {}
        for slot in slots:
            per_ref.setdefault(slot.source_ref, Slot)
            per_ref[slot.source_ref] |= slot
        for record in self:
            record.planning_slot_ids = per_ref.get(record._origin, Slot) if record.id else Slot
            record.planning_slot_count = len(record.planning_slot_ids)

    def _compute_planning_hours(self):
        for record in self:
            planned = sum(slot.allocated_hours * max(len(slot.resource_ids), 1)
                          for slot in record.planning_slot_ids)
            to_plan = record._planning_hours_to_plan()
            record.planning_hours_planned = planned
            record.planning_hours_to_plan = to_plan
            if not planned:
                record.planning_status = 'none'
            elif to_plan and planned + 0.001 < to_plan:
                record.planning_status = 'partial'
            else:
                record.planning_status = 'planned'

    def _planning_hours_to_plan(self):
        """ Hours the document needs (0 when it has no target). Override. """
        self.ensure_one()
        return 0.0

    def _planning_role(self):
        """ Role of the slots of the document. Override. """
        self.ensure_one()
        return self.env['om.planning.role']

    def _planning_slot_values(self):
        """ Default values of a new slot of the document. Override and call super. """
        self.ensure_one()
        values = {'source_ref': f'{self._name},{self.id}'}
        role = self._planning_role()
        if role:
            values['role_id'] = role.id
        if 'company_id' in self._fields and self.company_id:
            values['company_id'] = self.company_id.id
        return values

    def action_plan(self):
        """ Open the Gantt of the slots of the document, new slots linked to it. """
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_planning.action_om_planning_slot')
        context = {f'default_{key}': value for key, value in self._planning_slot_values().items()}
        context['om_planning_source'] = f'{self._name},{self.id}'
        action.update({
            'name': self.env._("Planning: %s", self.display_name),
            'domain': [('source_ref', '=', f'{self._name},{self.id}')],
            'context': context,
        })
        return action

    @api.ondelete(at_uninstall=False)
    def _unlink_planning_slots(self):
        self.env['om.planning.slot'].sudo().search(
            [('source_ref', 'in', self._planning_source_refs()), ('state', '=', 'draft')]).unlink()
