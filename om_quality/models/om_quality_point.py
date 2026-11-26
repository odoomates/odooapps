import random

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain

TEST_TYPES = [
    ('passfail', 'Pass / Fail'),
    ('measure', 'Measure'),
    ('template', 'Inspection Template'),
    ('picture', 'Photo'),
    ('instructions', 'Instructions'),
]

FREQUENCIES = [
    ('all', 'Every time'),
    ('nth', 'Every Nth time'),
    ('random', 'Random share'),
    ('lot', 'Once per lot / serial'),
    ('periodic', 'Every X days'),
]


class OmQualityPoint(models.Model):
    _name = 'om.quality.point'
    _description = 'Quality Control Point'
    _inherit = ['mail.thread']
    _order = 'sequence, id'
    _check_company_auto = True
    _rec_names_search = ['name', 'code']

    def _default_team_id(self):
        return self.env['om.quality.team'].search(
            [('company_id', 'in', self.env.companies.ids)], limit=1)

    name = fields.Char(string='Title', required=True, translate=True, tracking=True)
    code = fields.Char(string='Reference', readonly=True, copy=False, default='/')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company)
    team_id = fields.Many2one(
        'om.quality.team', string='Team', required=True, check_company=True, tracking=True,
        default=_default_team_id)
    user_id = fields.Many2one(
        'res.users', string='Responsible', check_company=True, tracking=True,
        domain="[('share', '=', False)]")
    point_type = fields.Selection(
        [('manual', 'On demand')], string='Where', required=True, default='manual', tracking=True,
        help="On demand: checks are created by hand from the point or a document.\n"
             "The inventory and manufacturing apps add transfers, manufacturing orders and work orders.")

    product_ids = fields.Many2many(
        'product.product', 'om_quality_point_product_rel', 'point_id', 'product_id', string='Products',
        check_company=True, help="Leave empty for every product.")
    product_category_ids = fields.Many2many(
        'product.category', 'om_quality_point_categ_rel', 'point_id', 'categ_id', string='Product Categories',
        help="Products of these categories and their sub-categories. Leave empty for every category.")
    partner_ids = fields.Many2many(
        'res.partner', 'om_quality_point_partner_rel', 'point_id', 'partner_id', string='Partners',
        check_company=True, help="Only for these vendors or customers. Leave empty for everyone.")

    test_type = fields.Selection(TEST_TYPES, string='Test', required=True, default='passfail', tracking=True)
    norm_min = fields.Float(string='Minimum', digits='Quality Measure')
    norm_target = fields.Float(string='Target', digits='Quality Measure')
    norm_max = fields.Float(string='Maximum', digits='Quality Measure')
    uom_id = fields.Many2one('uom.uom', string='Unit')
    samples = fields.Integer(default=1, help="How many values the operator records.")
    template_id = fields.Many2one('om.quality.test.template', string='Inspection Template', check_company=True)
    instructions = fields.Html(translate=True, help="Shown to the operator on the check.")
    instruction_file = fields.Binary(string='Instruction File', attachment=True)
    instruction_filename = fields.Char(string='Instruction File Name')

    frequency = fields.Selection(FREQUENCIES, string='How Often', required=True, default='all', tracking=True)
    frequency_nth = fields.Integer(string='Every', default=5)
    frequency_percent = fields.Float(string='Share (%)', default=10.0)
    frequency_days = fields.Integer(string='Every (Days)', default=7)
    occurrence_count = fields.Integer(
        string='Occurrences', readonly=True, copy=False,
        help="How many times the point matched a document; used by Every Nth time.")

    is_blocking = fields.Boolean(
        string='Blocking', tracking=True,
        help="The document cannot be validated or completed until the check passes, "
             "or a quality manager overrides it with a reason.")
    create_alert = fields.Boolean(
        string='Raise Non-conformance on Failure',
        default=lambda self: self.env.company.om_quality_alert_on_failure,
        help="A failed check raises a non-conformance for the team.")
    failure_message = fields.Text(
        translate=True, help="Shown to the operator when the check fails, e.g. what to do with the goods.")
    note = fields.Text(string='Internal Note')

    check_ids = fields.One2many('om.quality.check', 'point_id', string='Checks')
    check_count = fields.Integer(compute='_compute_check_stats', string='Checks Count')
    pass_rate = fields.Float(compute='_compute_check_stats', string='Pass Rate (%)')

    @api.depends('check_ids.state')
    def _compute_check_stats(self):
        data = {}
        for point, state, count in self.env['om.quality.check']._read_group(
                [('point_id', 'in', self.ids), ('state', 'in', ('todo', 'passed', 'failed'))],
                ['point_id', 'state'], ['__count']):
            data.setdefault(point.id, {})[state] = count
        for point in self:
            counts = data.get(point.id, {})
            point.check_count = sum(counts.values())
            done = counts.get('passed', 0) + counts.get('failed', 0)
            point.pass_rate = 100.0 * counts.get('passed', 0) / done if done else 0.0

    @api.constrains('frequency', 'frequency_nth', 'frequency_percent', 'frequency_days')
    def _check_frequency(self):
        for point in self:
            if point.frequency == 'nth' and point.frequency_nth < 1:
                raise ValidationError(self.env._("Every Nth time needs N of 1 or more."))
            if point.frequency == 'random' and not 0 < point.frequency_percent <= 100:
                raise ValidationError(self.env._("The random share must be between 0 and 100%."))
            if point.frequency == 'periodic' and point.frequency_days < 1:
                raise ValidationError(self.env._("Every X days needs at least one day."))

    @api.constrains('test_type', 'norm_min', 'norm_max', 'samples', 'template_id')
    def _check_test(self):
        for point in self:
            if point.test_type == 'measure':
                if point.norm_min > point.norm_max:
                    raise ValidationError(self.env._("The minimum is above the maximum."))
                if point.samples < 1:
                    raise ValidationError(self.env._("A measure needs at least one sample."))
            if point.test_type == 'template' and not point.template_id:
                raise ValidationError(self.env._("Choose the inspection template of the point %s.", point.name))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code') or vals['code'] == '/':
                vals['code'] = self.env['ir.sequence'].next_by_code('om.quality.point') or '/'
        return super().create(vals_list)

    def _compute_display_name(self):
        for point in self:
            point.display_name = f'{point.code} {point.name}' if point.code and point.code != '/' else point.name

    # ------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------

    @api.model
    def _get_points(self, point_type, company, extra_domain=None):
        """ The active points of a type in a company, to match against products with
        `_filter_product`. """
        domain = Domain('point_type', '=', point_type) & Domain('company_id', '=', company.id)
        if extra_domain:
            domain &= Domain(extra_domain)
        return self.sudo().search(domain)

    def _filter_product(self, product, partner=None):
        """ The points of `self` that apply to `product` and to `partner`. """
        partner = partner.commercial_partner_id if partner else partner

        def match(point):
            if point.product_ids and product not in point.product_ids:
                return False
            if point.product_category_ids:
                categ = product.categ_id
                ancestors = set(map(int, categ.parent_path.split('/')[:-1])) if categ.parent_path else {categ.id}
                if not ancestors & set(point.product_category_ids.ids):
                    return False
            if point.partner_ids:
                if not partner or partner not in point.partner_ids.commercial_partner_id:
                    return False
            return True
        return self.filtered(match)

    def _should_check(self, product):
        """ The frequency of the point says whether this occurrence gets a check. Once per lot
        is decided by the apps that know the lots: here it means every time. """
        self.ensure_one()
        if self.frequency == 'nth':
            count = self.occurrence_count + 1
            self.sudo().occurrence_count = count
            return count % self.frequency_nth == 0
        if self.frequency == 'random':
            return random.random() * 100.0 < self.frequency_percent
        if self.frequency == 'periodic':
            since = fields.Datetime.subtract(fields.Datetime.now(), days=self.frequency_days)
            return not self.env['om.quality.check'].sudo().search_count([
                ('point_id', '=', self.id), ('product_id', '=', product.id),
                ('state', '!=', 'cancel'), ('create_date', '>=', since)], limit=1)
        return True

    def _prepare_check_values(self, product=None, partner=None, document=None):
        """ Values of a new check of this point for `product` on `document`. """
        self.ensure_one()
        values = {
            'point_id': self.id,
            'company_id': self.company_id.id,
            'product_id': product.id if product else False,
            'partner_id': partner.commercial_partner_id.id if partner else False,
            'user_id': self.user_id.id,
        }
        if document:
            values.update({'res_model': document._name, 'res_id': document.id})
        return values

    # ------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------

    def action_view_checks(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_quality.action_om_quality_check')
        action['display_name'] = self.display_name
        action['domain'] = [('point_id', '=', self.id)]
        action['context'] = {'default_point_id': self.id, 'search_default_filter_not_cancel': 1}
        return action

    def action_create_check(self):
        """ A check by hand, from the point. """
        self.ensure_one()
        product = self.product_ids[:1]
        check = self.env['om.quality.check'].create(self._prepare_check_values(product=product))
        return check._action_open_dialog()
