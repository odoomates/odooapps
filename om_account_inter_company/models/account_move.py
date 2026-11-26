import logging

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command

_logger = logging.getLogger(__name__)

# the type of the document created in the other company
MIRROR_TYPES = {
    'out_invoice': 'in_invoice',
    'out_refund': 'in_refund',
    'in_invoice': 'out_invoice',
    'in_refund': 'out_refund',
}
TEXT_LINES = ('line_section', 'line_subsection', 'line_note')


class AccountMove(models.Model):
    _inherit = 'account.move'

    om_ic_source_move_id = fields.Many2one(
        'account.move', string="Inter-Company Source", copy=False, readonly=True, index='btree_not_null',
        ondelete='set null', help="The document of the other company this one was created from.")
    om_ic_mirror_ids = fields.One2many(
        'account.move', 'om_ic_source_move_id', string="Inter-Company Documents", readonly=True)
    om_ic_rule_id = fields.Many2one('om.inter.company.rule', string="Inter-Company Rule", copy=False, readonly=True)
    om_ic_warning = fields.Text(string="Inter-Company Warning", copy=False, readonly=True)
    om_ic_link_name = fields.Char(compute='_compute_om_ic_link', string="Inter-Company Document")
    om_ic_link_company = fields.Char(compute='_compute_om_ic_link', string="Inter-Company Company")

    @api.depends('om_ic_source_move_id', 'om_ic_mirror_ids')
    def _compute_om_ic_link(self):
        for move in self:
            linked = move.sudo()._om_ic_linked_moves()
            move.om_ic_link_name = ', '.join(m._om_ic_label() for m in linked) if linked else False
            move.om_ic_link_company = ', '.join(linked.company_id.mapped('name')) if linked else False

    def _om_ic_label(self):
        """The number of the document, or what it is while in draft."""
        self.ensure_one()
        if self.name and self.name != '/':
            return self.name
        labels = {'out_invoice': self.env._("Draft Invoice"), 'out_refund': self.env._("Draft Credit Note"),
                  'in_invoice': self.env._("Draft Bill"), 'in_refund': self.env._("Draft Refund")}
        return labels.get(self.move_type, self.env._("Draft"))

    def _om_ic_linked_moves(self):
        """The documents of the other companies linked with this one: its source, or those made from it."""
        self.ensure_one()
        return self.om_ic_source_move_id or self.om_ic_mirror_ids

    # ------------------------------------------------------------------
    # Posting: the document is created in the other company
    # ------------------------------------------------------------------

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        if not self.env.context.get('om_ic_no_mirror'):
            sources = posted.filtered(
                lambda m: m.move_type in MIRROR_TYPES and not m.om_ic_source_move_id and m.state == 'posted')
            if sources:
                sources._om_ic_mirror()
        return posted

    def _om_ic_rule(self):
        """(rule, company receiving the document) for this posted document, or (empty, False)."""
        self.ensure_one()
        Rule = self.env['om.inter.company.rule']
        move = self.sudo()
        target = move.commercial_partner_id._om_ic_company() if move.commercial_partner_id else False
        if not target or target == move.company_id:
            return Rule, False
        rule = Rule._om_ic_get(move.company_id, target)
        if not rule:
            return Rule, False
        if move.is_sale_document() and not rule.mirror_invoices:
            return Rule, False
        if move.is_purchase_document() and not rule.mirror_bills:
            return Rule, False
        return rule, target

    def _om_ic_mirror(self):
        """Create, or bring up to date, the document of the other company for each of these documents."""
        for move in self:
            rule, target = move._om_ic_rule()
            if not rule:
                continue
            mirrors = move.sudo().om_ic_mirror_ids.filtered(lambda m: m.company_id == target)
            try:
                with self.env.cr.savepoint():
                    if mirrors:
                        move._om_ic_resync(mirrors[0], rule)
                    else:
                        move._om_ic_create_mirror(rule, target)
                    move.sudo().om_ic_warning = False
            except (UserError, ValidationError, AccessError) as error:
                _logger.info("Inter-company document of %s not created: %s", move.name, error)
                move.sudo().om_ic_warning = self.env._(
                    "The document could not be created in %(company)s: %(error)s",
                    company=target.name, error=error.args[0] if error.args else str(error))
                move.sudo().message_post(body=move.om_ic_warning)

    def action_om_ic_retry(self):
        """Try again to create the document of the other company (after fixing what prevented it)."""
        for move in self.filtered(lambda m: m.state == 'posted' and not m.om_ic_source_move_id):
            move._om_ic_mirror()
        return True

    def action_om_ic_dismiss(self):
        self.sudo().om_ic_warning = False
        return True

    def _om_ic_mirror_type(self):
        return MIRROR_TYPES[self.move_type]

    def _om_ic_prepare_mirror_vals(self, rule, target, env):
        """The values of the document of ``target`` made from this one, in ``env`` (that of the user of the
        rule in ``target``)."""
        self.ensure_one()
        source = self.sudo()
        move_type = source._om_ic_mirror_type()
        is_sale = move_type in ('out_invoice', 'out_refund')
        journal = rule._om_ic_journal(target, 'sale' if is_sale else 'purchase')
        if not journal:
            raise UserError(self.env._("%(company)s has no %(type)s journal.", company=target.name,
                                       type=self.env._("sales") if is_sale else self.env._("purchase")))
        partner = source.company_id.partner_id.sudo().with_company(target)
        currency = source.currency_id if rule.currency_mode == 'source' else target.currency_id
        rate_date = source.invoice_date or source.date
        fiscal_position = env['account.fiscal.position'].sudo().with_company(target)._get_fiscal_position(partner)
        vals = {
            'move_type': move_type,
            'partner_id': partner.id,
            'journal_id': journal.id,
            'company_id': target.id,
            'invoice_date': source.invoice_date,
            'currency_id': currency.id,
            'fiscal_position_id': fiscal_position.id,
            'invoice_origin': source.invoice_origin or source.name,
            'om_ic_source_move_id': source.id,
            'om_ic_rule_id': rule.id,
            'invoice_line_ids': [],
        }
        if is_sale:
            vals['ref'] = source.ref or source.name
        else:
            vals['ref'] = source.name
            vals['payment_reference'] = source.payment_reference or source.name
        if source.invoice_date_due:
            vals.update(invoice_payment_term_id=False, invoice_date_due=source.invoice_date_due)
        reversed_mirror = source.reversed_entry_id.om_ic_mirror_ids.filtered(lambda m: m.company_id == target)[:1]
        if reversed_mirror:
            vals['reversed_entry_id'] = reversed_mirror.id
        for line in source.invoice_line_ids:
            line_vals = source._om_ic_prepare_mirror_line_vals(
                line, rule, target, journal, is_sale, fiscal_position, currency, rate_date)
            if line_vals:
                vals['invoice_line_ids'].append(Command.create(line_vals))
        return vals

    def _om_ic_prepare_mirror_line_vals(self, line, rule, target, journal, is_sale, fiscal_position, currency,
                                        rate_date):
        """The values of the line of the document of ``target`` made from ``line``, or None to leave it out."""
        if line.display_type in TEXT_LINES:
            return {'display_type': line.display_type, 'name': line.name, 'sequence': line.sequence}
        if line.display_type != 'product':
            return None
        product = rule._om_ic_map_product(line.product_id, target)
        taxes = rule._om_ic_map_taxes(line.tax_ids, target, 'sale' if is_sale else 'purchase', product,
                                      fiscal_position)
        price_unit = line.price_unit
        if currency != line.currency_id:
            price_unit = line.currency_id._convert(price_unit, currency, target, rate_date, round=False)
        vals = {
            'display_type': 'product',
            'sequence': line.sequence,
            'name': line.name,
            'product_id': product.id,
            'quantity': line.quantity,
            'product_uom_id': line.product_uom_id.id,
            'price_unit': price_unit,
            'discount': line.discount,
            'tax_ids': [Command.set(taxes.ids)],
        }
        account = rule._om_ic_map_account(line.account_id, target, line.company_id)
        if account:
            vals['account_id'] = account.id
        elif not product and journal.default_account_id:
            vals['account_id'] = journal.default_account_id.id
        distribution = rule._om_ic_map_analytic(line.analytic_distribution, target)
        if distribution:
            vals['analytic_distribution'] = distribution
        return vals

    def _om_ic_create_mirror(self, rule, target):
        self.ensure_one()
        source = self.sudo()
        env = rule._om_ic_env(target)
        vals = source._om_ic_prepare_mirror_vals(rule, target, env)
        mirror = env['account.move'].with_context(default_move_type=vals['move_type']).create(vals)
        if rule.copy_pdf:
            source._om_ic_attach_pdf(mirror)
        if rule.target_state == 'posted':
            mirror.action_post()
        source._om_ic_log_created(mirror)
        return mirror

    def _om_ic_resync(self, mirror, rule):
        """This document was posted again: its document in the other company follows when it is still in
        draft (or cancelled, when the rule follows), else it is warned."""
        self.ensure_one()
        source = self.sudo()
        env = rule._om_ic_env(mirror.company_id)
        mirror = mirror.with_env(env)
        if mirror.state == 'cancel' and rule.on_source_change == 'follow':
            mirror.button_draft()
        if mirror.state == 'draft':
            vals = source._om_ic_prepare_mirror_vals(rule, mirror.company_id, env)
            lines = vals.pop('invoice_line_ids')
            for key in ('move_type', 'company_id', 'om_ic_source_move_id', 'om_ic_rule_id', 'partner_id'):
                vals.pop(key, None)
            mirror.write({
                **vals,
                'om_ic_warning': False,
                'invoice_line_ids': [Command.unlink(line.id) for line in mirror.invoice_line_ids] + lines,
            })
            if rule.target_state == 'posted':
                mirror.action_post()
            mirror.message_post(body=self.env._(
                "Updated from %(document)s of %(company)s, posted again.",
                document=source._get_html_link(), company=source.company_id.name))
            return
        if not source._om_ic_same_total(mirror):
            mirror._om_ic_warn(self.env._(
                "%(document)s of %(company)s was posted again with a total of %(total)s: check this document.",
                document=source.name, company=source.company_id.name,
                total=source.currency_id.format(source.amount_total)))
        else:
            mirror.sudo().om_ic_warning = False

    def _om_ic_same_total(self, mirror):
        """Whether ``mirror`` has the total of this document, converted when in another currency (each line
        converted on its own may differ by a rounding)."""
        self.ensure_one()
        source = self.sudo()
        currency = mirror.currency_id
        total = source.amount_total
        if source.currency_id != currency:
            total = source.currency_id._convert(
                total, currency, mirror.company_id, source.invoice_date or source.date, round=False)
        tolerance = currency.rounding * (len(source.invoice_line_ids) + 1)
        return abs(total - mirror.amount_total) <= tolerance

    def _om_ic_attach_pdf(self, mirror):
        """Attach the PDF of this invoice to ``mirror``, as its original document."""
        self.ensure_one()
        source = self.sudo()
        try:
            if source.invoice_pdf_report_id:
                content, name = source.invoice_pdf_report_id.raw, source.invoice_pdf_report_id.name
            else:
                content, _report_type = self.env['ir.actions.report'].sudo().with_company(
                    source.company_id)._render_qweb_pdf('account.account_invoices', source.ids)
                name = source._get_invoice_report_filename()
        except (UserError, OSError) as error:
            _logger.info("Inter-company: no PDF for %s: %s", source.name, error)
            return
        attachment = self.env['ir.attachment'].sudo().create({
            'name': name,
            'raw': content,
            'mimetype': 'application/pdf',
            'res_model': 'account.move',
            'res_id': mirror.id,
            'company_id': mirror.company_id.id,
        })
        mirror.sudo().message_main_attachment_id = attachment

    def _om_ic_log_created(self, mirror):
        source = self.sudo()
        mirror.sudo().message_post(body=self.env._(
            "Created from %(document)s of %(company)s.", document=source._get_html_link(),
            company=source.company_id.name), attachment_ids=mirror.sudo().message_main_attachment_id.ids)
        source.message_post(body=self.env._(
            "%(document)s created in %(company)s.", document=mirror.sudo()._get_html_link(),
            company=mirror.company_id.name))

    # ------------------------------------------------------------------
    # Reset to draft and cancel: the other company follows or is warned
    # ------------------------------------------------------------------

    def button_draft(self):
        res = super().button_draft()
        if self.env.context.get('om_ic_no_mirror') or self.env.context.get('om_ic_cancelling'):
            return res
        notices = self._om_ic_changed('draft')
        return self._om_ic_notice_action(notices) or res

    def button_cancel(self):
        res = super(AccountMove, self.with_context(om_ic_cancelling=True)).button_cancel()
        if self.env.context.get('om_ic_no_mirror'):
            return res
        notices = self._om_ic_changed('cancel')
        return self._om_ic_notice_action(notices) or res

    def _om_ic_changed(self, event):
        """These documents were reset to draft (``event`` 'draft') or cancelled ('cancel'): their documents
        in the other companies follow, or are warned, as their rule says. Returns what the user is told."""
        notices = []
        for move in self.sudo():
            for mirror in move.om_ic_mirror_ids.filtered(lambda m: m.state != 'cancel'):
                notices.append(move._om_ic_follow(mirror, event))
            source = move.om_ic_source_move_id
            if source and source.state == 'posted':
                text = self.env._(
                    "%(document)s of %(company)s, created from this document, was reset to draft.",
                    document=move._om_ic_label(), company=move.company_id.name) if event == 'draft' else self.env._(
                    "%(document)s of %(company)s, created from this document, was cancelled.",
                    document=move._om_ic_label(), company=move.company_id.name)
                source._om_ic_warn(text)
                notices.append(self.env._("%(document)s of %(company)s, which this document was created from, "
                                          "is still posted.", document=source.name, company=source.company_id.name))
        return [notice for notice in notices if notice]

    def _om_ic_follow(self, mirror, event):
        self.ensure_one()
        rule = mirror.om_ic_rule_id
        what = self.env._("reset to draft") if event == 'draft' else self.env._("cancelled")
        paid = mirror.payment_state in ('paid', 'in_payment', 'partial', 'reversed')
        if rule.on_source_change == 'follow' and not paid and not (event == 'draft' and mirror.state == 'draft'):
            try:
                with self.env.cr.savepoint():
                    mirror_env = mirror.with_env(rule._om_ic_env(mirror.company_id))
                    if event == 'draft':
                        mirror_env.button_draft()
                    else:
                        mirror_env.button_cancel()
                mirror.message_post(body=self.env._(
                    "%(what)s as %(document)s of %(company)s was.", what=what.capitalize(),
                    document=self._get_html_link(), company=self.company_id.name))
                return self.env._("%(document)s of %(company)s was %(what)s too.", document=mirror._om_ic_label(),
                                  company=mirror.company_id.name, what=what)
            except (UserError, ValidationError, AccessError) as error:
                _logger.info("Inter-company: %s not followed: %s", mirror.name, error)
        if event == 'draft' and mirror.state == 'draft':
            return False
        mirror._om_ic_warn(self.env._(
            "%(document)s of %(company)s, which this document was created from, was %(what)s.",
            document=self.name, company=self.company_id.name, what=what))
        return self.env._("%(document)s of %(company)s, created from this document, is unchanged: check it.",
                          document=mirror._om_ic_label(), company=mirror.company_id.name)

    def _om_ic_warn(self, text):
        for move in self.sudo():
            move.om_ic_warning = text
            move.message_post(body=Markup('<p class="text-warning">%s</p>') % text)

    def _om_ic_notice_action(self, notices):
        if not notices:
            return False
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._("Inter-Company"),
                'message': '\n'.join(notices),
                'type': 'warning',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    # ------------------------------------------------------------------
    # Smart button
    # ------------------------------------------------------------------

    def action_om_ic_open(self):
        self.ensure_one()
        linked = self.sudo()._om_ic_linked_moves()
        if not linked:
            return False
        if linked.company_id - self.env.user.company_ids:
            raise UserError(self.env._(
                "%(documents)s is in %(company)s, a company you have no access to.",
                documents=', '.join(m._om_ic_label() for m in linked), company=', '.join(linked.company_id.mapped('name'))))
        action = {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'name': self.env._("Inter-Company"),
            'context': {'create': False},
        }
        if len(linked) == 1:
            action.update(res_id=linked.id, views=[(False, 'form')], view_mode='form')
        else:
            action.update(domain=[('id', 'in', linked.ids)], views=[(False, 'list'), (False, 'form')],
                          view_mode='list,form')
        return action
