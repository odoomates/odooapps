from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_round


class OmConnectorBackendMixin(models.AbstractModel):
    """ A connection to an external system: a Shopify store, a WooCommerce site, a marketplace
    account… Its jobs are queued with ``_connector_enqueue`` and shown from its form. """
    _name = 'om.connector.backend.mixin'
    _description = 'Connector Connection'

    connector_job_todo_count = fields.Integer(string='Jobs To Do', compute='_compute_connector_job_counts')
    connector_job_failed_count = fields.Integer(string='Failed Jobs', compute='_compute_connector_job_counts')

    def _compute_connector_job_counts(self):
        counts = {
            (backend_id, state): count
            for backend_id, state, count in self.env['om.connector.job'].sudo()._read_group(
                [('backend_model', '=', self._name), ('backend_id', 'in', self.ids),
                 ('state', 'in', ('pending', 'failed'))],
                ['backend_id', 'state'], ['__count'])
        }
        for backend in self:
            backend.connector_job_todo_count = counts.get((backend.id, 'pending'), 0)
            backend.connector_job_failed_count = counts.get((backend.id, 'failed'), 0)

    def _connector_enqueue(self, method_name, payload=None, **kwargs):
        """ Queue ``method_name`` (on this model, or on ``model_name``) for this connection.
        See ``om.connector.job._enqueue`` for the options. """
        self.ensure_one()
        return self.env['om.connector.job']._enqueue(self, method_name, payload, **kwargs)

    def _connector_enqueue_once(self, method_name, payload=None, **kwargs):
        """ Queue ``method_name`` unless a job of this method is already to do for this connection:
        for the scheduled work (fetch the new orders…), which must not pile up. """
        self.ensure_one()
        pending = self.env['om.connector.job'].sudo().search(
            self._connector_job_domain() + [('method_name', '=', method_name), ('state', '=', 'pending')], limit=1)
        return pending or self._connector_enqueue(method_name, payload, **kwargs)

    def _connector_job_failed(self, job):
        """ Called when ``job`` of this connection fails for good. """

    # ------------------------------------------------------------------
    # Orders: pricelist and taxes (the connection has a ``company_id``)
    # ------------------------------------------------------------------

    def _connector_pricelist(self, currency_code, label):
        """ A pricelist in the currency ``currency_code`` of an order, when it is not the currency of
        the company (found, or created as "<label> <currency>"). """
        self.ensure_one()
        if not currency_code or currency_code == self.company_id.currency_id.name:
            return self.env['product.pricelist']
        currency = self.env['res.currency'].with_context(active_test=False).search([('name', '=', currency_code)],
                                                                                   limit=1)
        if not currency:
            raise UserError(_("Unknown currency %(currency)s.", currency=currency_code))
        if not currency.active:
            currency.sudo().active = True
        Pricelist = self.env['product.pricelist'].sudo()
        return Pricelist.search([('currency_id', '=', currency.id), ('company_id', 'in', [False, self.company_id.id])],
                                limit=1) or Pricelist.create({
                                    'name': f"{label} {currency.name}",
                                    'currency_id': currency.id, 'company_id': self.company_id.id})

    def _connector_taxes(self, rates, included, account=None):
        """ The Odoo sale taxes of ``rates``, found or created.

        :param rates: ``[(percent, title)]``, e.g. ``[(10.0, 'State Tax')]``
        :param included: the prices of the order include the taxes
        :param account: the tax account of the taxes created, else the one of the company """
        self.ensure_one()
        Tax = self.env['account.tax'].sudo().with_company(self.company_id)
        taxes = Tax.browse()
        for percent, title in rates or []:
            rate = float_round(float(percent or 0.0), precision_digits=4)
            if not rate:
                continue
            candidates = Tax.search([
                ('company_id', '=', self.company_id.id), ('type_tax_use', '=', 'sale'),
                ('amount_type', '=', 'percent'), ('amount', '=', rate),
            ])
            tax = candidates.filtered(lambda t: t.price_include == included)[:1]
            if not tax:
                tax = Tax.create({
                    'name': f"{title or _('Tax')} {rate:g}%" + (_(" (included)") if included else ''),
                    'amount': rate,
                    'amount_type': 'percent',
                    'type_tax_use': 'sale',
                    'price_include_override': 'tax_included' if included else 'tax_excluded',
                    'company_id': self.company_id.id,
                    'country_id': self.company_id.account_fiscal_country_id.id,
                })
                if account:
                    (tax.invoice_repartition_line_ids | tax.refund_repartition_line_ids).filtered(
                        lambda l: l.repartition_type == 'tax').account_id = account
            taxes |= tax
        return taxes

    def _connector_activity(self, summary, note, once=True):
        """ An activity for the responsible of the connection (``responsible_id``, else its creator);
        with ``once``, not while one with this summary is open. """
        self.ensure_one()
        if once and self.activity_ids.filtered(lambda a: a.summary == summary):
            return
        responsible = self.responsible_id if 'responsible_id' in self._fields else self.env['res.users']
        self.activity_schedule('mail.mail_activity_data_todo', summary=summary, note=note,
                               user_id=(responsible or self.create_uid or self.env.user).id)

    def _connector_job_domain(self):
        return [('backend_model', '=', self._name), ('backend_id', 'in', self.ids)]

    def action_open_connector_jobs(self):
        action = self.env['ir.actions.act_window']._for_xml_id('om_connector_base.om_connector_job_action')
        action['domain'] = self._connector_job_domain()
        action['context'] = {'search_default_filter_todo_failed': 1}
        if len(self) == 1:
            action['display_name'] = _("Jobs of %(connection)s", connection=self.display_name)
        return action

    def unlink(self):
        self.env['om.connector.job'].sudo().search(self._connector_job_domain()).unlink()
        return super().unlink()
