from odoo import api, fields, models


class OmFsEquipment(models.Model):
    """ A piece of equipment at a customer site: installed on a job, serviced on the next ones. """
    _name = 'om.fs.equipment'
    _description = "Equipment at Customer Site"
    _inherit = ['mail.thread']
    _order = 'partner_id, installed_on desc, id desc'

    name = fields.Char(compute='_compute_name', store=True, precompute=True, readonly=False, required=True)
    active = fields.Boolean(default=True)
    partner_id = fields.Many2one('res.partner', string="Site", required=True, index=True, tracking=True)
    commercial_partner_id = fields.Many2one(related='partner_id.commercial_partner_id', store=True,
                                            string="Customer")
    product_id = fields.Many2one('product.product', string="Product", tracking=True)
    lot_id = fields.Many2one('stock.lot', string="Serial Number", tracking=True,
                             domain="[('product_id', '=', product_id)]")
    installed_on = fields.Date(string="Installed On", tracking=True)
    install_task_id = fields.Many2one('project.task', string="Installation Job", index='btree_not_null')
    job_ids = fields.One2many('project.task', 'equipment_id', string="Jobs")
    job_count = fields.Integer(compute='_compute_job_count', string="Job Count")
    note = fields.Text(string="Notes", help="Where it is on site, warranty, access...")
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.company)

    @api.depends('product_id', 'lot_id')
    def _compute_name(self):
        for equipment in self:
            if equipment.product_id:
                name = equipment.product_id.display_name
                equipment.name = f'{name} ({equipment.lot_id.name})' if equipment.lot_id else name

    @api.depends('job_ids')
    def _compute_job_count(self):
        for equipment in self:
            equipment.job_count = len(equipment.job_ids)

    def action_view_jobs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_field_service.action_om_fs_job')
        action['domain'] = [('equipment_id', '=', self.id)]
        action['context'] = {
            'default_equipment_id': self.id,
            'default_partner_id': self.commercial_partner_id.id,
            'default_site_partner_id': self.partner_id.id,
            'om_fs_job': True,
        }
        return action

    def _fs_text(self):
        """ Text of the equipment for the job. """
        self.ensure_one()
        parts = [self.name]
        if self.note:
            parts.append(self.note)
        return '\n'.join(parts)
