from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class ProjectTask(models.Model):
    _inherit = 'project.task'

    is_covered = fields.Boolean(
        string="Covered", tracking=True, copy=False,
        help="The job is covered by a warranty or a contract: its time is not billed and its parts are not "
             "billed unless marked as billable.")
    coverage = fields.Selection([
        ('warranty', 'Warranty'),
        ('contract', 'Maintenance Contract'),
        ('goodwill', 'Goodwill'),
    ], string="Covered By", copy=False)
    fs_sale_order_id = fields.Many2one(
        'sale.order', string="Job Sales Order", copy=False, index='btree_not_null', tracking=True,
        help="Sales order of the time and material of the job.")
    fs_followup_order_ids = fields.One2many('sale.order', 'fs_origin_task_id', string="Follow-up Quotations")
    fs_followup_count = fields.Integer(compute='_compute_fs_followup_count', string="Follow-up Count")

    @api.depends('fs_followup_order_ids')
    def _compute_fs_followup_count(self):
        for task in self:
            task.fs_followup_count = len(task.fs_followup_order_ids)

    def _get_last_sol_of_customer_domain(self):
        # a covered job is not linked to the open order of the customer
        if self.is_field_service and self.is_covered:
            return []
        return super()._get_last_sol_of_customer_domain()

    def write(self, vals):
        if vals.get('is_covered'):
            vals = {**vals, 'sale_line_id': False}
        res = super().write(vals)
        if vals.get('sale_line_id'):
            for task in self.filtered(lambda t: t.is_field_service and not t.fs_sale_order_id):
                task.fs_sale_order_id = task.sale_line_id.order_id
        if 'is_covered' in vals:
            # the timesheets follow: billed again once the job has a sales order item
            self.filtered('is_field_service').timesheet_ids.filtered(
                lambda line: not line.is_so_line_edited and line._is_not_billed())._compute_so_line()
        return res

    # ------------------------------------------------------------------
    # Sales order
    # ------------------------------------------------------------------

    def _fs_service_product(self):
        self.ensure_one()
        return self.job_type_id.service_product_id or self.env.ref(
            'om_field_service_sale.product_fs_hour', raise_if_not_found=False)

    def _fs_sale_order_values(self):
        self.ensure_one()
        partner = self.partner_id
        return {
            'partner_id': partner.id,
            'partner_shipping_id': (self.site_partner_id or partner).id,
            'origin': self.job_number or self.name,
            'company_id': self._fs_company().id,
        }

    def _fs_ensure_sale_order(self):
        """ The confirmed sales order of the job, created with the line of its service product. """
        self.ensure_one()
        if not self.partner_id:
            raise UserError(self.env._("Set the customer of %s first.", self.display_name))
        order = self.fs_sale_order_id or self.sale_order_id
        if not order:
            order = self.env['sale.order'].sudo().create(self._fs_sale_order_values())
        if order.state == 'draft' or order.state == 'sent':
            order.action_confirm()
        if not self.is_covered and not self.sale_line_id:
            product = self._fs_service_product()
            if product:
                line = order.order_line.filtered(lambda l: l.product_id == product)[:1] or \
                    self.env['sale.order.line'].sudo().create({
                        'order_id': order.id,
                        'product_id': product.id,
                        'product_uom_qty': 0.0,
                        'name': self._fs_line_reference(),
                    })
                self.sudo().sale_line_id = line
        if self.fs_sale_order_id != order:
            self.sudo().fs_sale_order_id = order
        return order

    def action_fs_create_sale_order(self):
        self.ensure_one()
        order = self._fs_ensure_sale_order()
        return self._fs_open_order(order)

    def action_fs_view_sale_order(self):
        self.ensure_one()
        return self._fs_open_order(self.fs_sale_order_id)

    def _fs_open_order(self, order):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': order.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    def action_fs_quote_followup(self):
        """ A quotation for work found on site, linked to the job. """
        self.ensure_one()
        if not self.partner_id:
            raise UserError(self.env._("Set the customer of %s first.", self.display_name))
        values = self._fs_sale_order_values()
        values.update({
            'origin': self.env._("%s (follow-up)", self.job_number or self.name),
            'fs_origin_task_id': self.id,
        })
        order = self.env['sale.order'].create(values)
        return self._fs_open_order(order)

    def action_fs_view_followups(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('sale.action_quotations_with_onboarding')
        action['domain'] = [('fs_origin_task_id', '=', self.id)]
        action['context'] = {'default_fs_origin_task_id': self.id, 'default_partner_id': self.partner_id.id}
        return action

    # ------------------------------------------------------------------
    # Done: parts to the order
    # ------------------------------------------------------------------

    def _fs_on_done(self):
        for job in self.sudo():
            parts = job.part_ids.filtered(
                lambda p: p.state == 'draft' and p.is_billable and not p.sale_line_id and p.product_id.sale_ok)
            billable_time = not job.is_covered and job.timesheet_ids
            if not (parts or billable_time):
                continue
            order = job._fs_ensure_sale_order()
            SaleLine = self.env['sale.order.line'].sudo().with_context(skip_procurement=True)
            for part in parts:
                part.sale_line_id = SaleLine.create({
                    'order_id': order.id,
                    'product_id': part.product_id.id,
                    'name': job._fs_part_line_name(part),
                    'product_uom_qty': part.quantity,
                    'product_uom_id': part.product_uom_id.id,
                })
        return super()._fs_on_done()

    def _fs_line_reference(self):
        self.ensure_one()
        return self.env._("Job %(number)s: %(name)s", number=self.job_number or '', name=self.name)

    def _fs_part_line_name(self, part):
        if part.lot_id:
            return self.env._("%(job)s, serial %(lot)s", job=self._fs_line_reference(), lot=part.lot_id.name)
        return self._fs_line_reference()

    def _fs_part_move_values(self, part, picking):
        values = super()._fs_part_move_values(part, picking)
        if part.sale_line_id:
            values['sale_line_id'] = part.sale_line_id.id
        return values

    def _fs_mobile_data(self):
        data = super()._fs_mobile_data()
        data['extra']['covered'] = self.is_covered
        return data
