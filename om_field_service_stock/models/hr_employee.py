from odoo import fields, models
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    van_location_id = fields.Many2one(
        'stock.location', string="Van Stock", domain="[('usage', '=', 'internal')]",
        help="Stock location of the van of the technician: the parts they use are taken from it.")

    def action_create_van_location(self):
        for employee in self.filtered(lambda e: not e.van_location_id):
            company = employee.company_id or self.env.company
            warehouse = self.env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
            if not warehouse:
                raise UserError(self.env._("Create a warehouse first."))
            parent = self.env['stock.location'].search([
                ('name', '=', 'Vans'), ('location_id', '=', warehouse.view_location_id.id),
                ('company_id', '=', company.id),
            ], limit=1) or self.env['stock.location'].create({
                'name': 'Vans',
                'usage': 'view',
                'location_id': warehouse.view_location_id.id,
                'company_id': company.id,
            })
            employee.van_location_id = self.env['stock.location'].create({
                'name': employee.name,
                'usage': 'internal',
                'location_id': parent.id,
                'company_id': company.id,
            })
        return True

    def action_view_van_stock(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_field_service_stock.action_om_fs_van_stock')
        action['domain'] = [('location_id', 'child_of', self.van_location_id.id)]
        action['name'] = self.env._("Van Stock: %s", self.name)
        return action

    def action_replenish_van(self):
        self.ensure_one()
        if not self.van_location_id:
            raise UserError(self.env._("%s has no van stock location.", self.name))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Replenish the Van of %s", self.name),
            'res_model': 'om.fs.van.replenish',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_employee_id': self.id},
        }
