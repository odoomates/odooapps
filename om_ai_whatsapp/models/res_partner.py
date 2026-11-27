from datetime import timedelta

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    om_ai_whatsapp_verified_number = fields.Char(
        'WhatsApp Verified Number', readonly=True, copy=False, groups='base.group_user')
    om_ai_whatsapp_verified_date = fields.Datetime(
        'WhatsApp Verified On', readonly=True, copy=False, groups='base.group_user')
    om_ai_whatsapp_verified = fields.Boolean(
        'WhatsApp Verified', compute='_compute_om_ai_whatsapp_verified', inverse='_inverse_om_ai_whatsapp_verified',
        groups='base.group_user',
        help="The WhatsApp assistant shows invoices, balance and addresses to this number. Set when the customer "
             "typed the code mailed to them, or by hand; it lasts the days set on the WhatsApp account.")

    @api.depends('om_ai_whatsapp_verified_number', 'om_ai_whatsapp_verified_date', 'phone_sanitized')
    def _compute_om_ai_whatsapp_verified(self):
        for partner in self:
            partner.om_ai_whatsapp_verified = partner._om_ai_whatsapp_is_verified(partner.phone_sanitized)

    def _inverse_om_ai_whatsapp_verified(self):
        for partner in self:
            if partner.om_ai_whatsapp_verified and partner.phone_sanitized:
                partner._om_ai_whatsapp_set_verified(
                    partner.phone_sanitized, self.env._('Marked as WhatsApp verified by %s.', self.env.user.name))
            elif not partner.om_ai_whatsapp_verified and partner.sudo().om_ai_whatsapp_verified_number:
                partner.sudo().write({'om_ai_whatsapp_verified_number': False, 'om_ai_whatsapp_verified_date': False})
                partner.message_post(body=self.env._('WhatsApp verification removed by %s.', self.env.user.name))

    def _om_ai_whatsapp_is_verified(self, number, days=None):
        """ Whether ``number`` was verified for this contact in the last ``days``. """
        self.ensure_one()
        partner = self.sudo()
        clean = self.env['om.whatsapp.account']._om_whatsapp_clean_number
        if not number or not partner.om_ai_whatsapp_verified_date or \
                clean(partner.om_ai_whatsapp_verified_number or '') != clean(number):
            return False
        if days is None:
            accounts = self.env['om.whatsapp.account'].sudo().search([('om_ai_active', '=', True)])
            days = max(accounts.mapped('om_ai_verify_days') or [30])
        return partner.om_ai_whatsapp_verified_date >= fields.Datetime.now() - timedelta(days=days or 30)

    def _om_ai_whatsapp_set_verified(self, number, note):
        self.ensure_one()
        clean = self.env['om.whatsapp.account']._om_whatsapp_clean_number
        self.sudo().write({'om_ai_whatsapp_verified_number': clean(number),
                           'om_ai_whatsapp_verified_date': fields.Datetime.now()})
        self.sudo().message_post(body=note)
