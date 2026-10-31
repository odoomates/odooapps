import hashlib
import secrets
import uuid
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import consteq, email_normalize

from .sign_request_signer import CODE_ATTEMPTS, CODE_MINUTES, CODE_RESEND_SECONDS

# how many links a visitor may ask by hour, by email and by IP address, when not set in the system parameters
SHARE_LIMIT_EMAIL = 5
SHARE_LIMIT_IP = 20
CODE_SENDS = 3  # codes sent for one visit at most
NAME_LIMIT = 128


class SignShareVisit(models.Model):
    """ A visitor of the shared link of a template: their name and email, the code emailed to them, and the request
    made once they entered it. Made as the super user from the public page only; kept to limit how many requests a
    visitor makes. """
    _name = 'sign.share.visit'
    _description = 'Shared Link Visit'
    _order = 'id desc'

    template_id = fields.Many2one('sign.template', required=True, ondelete='cascade', index=True, readonly=True)
    company_id = fields.Many2one(related='template_id.company_id', store=True, index=True)
    name = fields.Char(required=True, readonly=True)
    email = fields.Char(required=True, readonly=True, index=True, help='Normalized.')
    ip = fields.Char(string='IP Address', readonly=True, index=True)
    access_token = fields.Char(required=True, readonly=True, copy=False, groups='base.group_system')
    code_hash = fields.Char(readonly=True, copy=False, groups='base.group_system')
    code_expiry = fields.Datetime(readonly=True, copy=False)
    code_attempts = fields.Integer(readonly=True, copy=False)
    code_sends = fields.Integer(readonly=True, copy=False)
    request_id = fields.Many2one('sign.request', readonly=True, ondelete='set null', index='btree_not_null')

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise UserError(self.env._('A visit is made by the visitor of a shared link.'))
        for vals in vals_list:
            vals['access_token'] = uuid.uuid4().hex
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            raise UserError(self.env._('A visit is made by the visitor of a shared link.'))
        return super().write(vals)

    @api.autovacuum
    def _gc_visits(self):
        """ The visits that made no request are no longer needed after a few days. """
        self.sudo().search([('request_id', '=', False),
                            ('create_date', '<', fields.Datetime.now() - timedelta(days=7))]).unlink()

    # ------------------------------------------------------------------
    # The visitor asks for a code
    # ------------------------------------------------------------------

    @api.model
    def _limits(self):
        params = self.env['ir.config_parameter'].sudo()
        return (max(params.get_int('om_sign.share_limit_email', SHARE_LIMIT_EMAIL), 0),
                max(params.get_int('om_sign.share_limit_ip', SHARE_LIMIT_IP), 0))

    @api.model
    def _check_limits(self, email, ip):
        """ :raise UserError: when the email or the IP address asked for too many links in the last hour """
        by_email, by_ip = self._limits()
        since = fields.Datetime.now() - timedelta(hours=1)
        Visit = self.sudo()
        if Visit.search_count([('email', '=', email), ('create_date', '>=', since)]) >= by_email or \
                (ip and Visit.search_count([('ip', '=', ip), ('create_date', '>=', since)]) >= by_ip):
            raise UserError(self.env._('Too many requests: try again in an hour.'))

    @api.model
    def _start(self, template, name, email, ip):
        """ A visitor of the link of `template` gives their name and email: a code is emailed to them.

        :return: the visit
        :raise UserError: when the name or the email is missing, or too many requests were made """
        name = (name or '').strip()[:NAME_LIMIT]
        normalized = email_normalize(email or '')
        if not name:
            raise UserError(self.env._('Write your name.'))
        if not normalized:
            raise UserError(self.env._('Write a valid email address.'))
        self._check_limits(normalized, ip)
        visit = self.sudo().create({'template_id': template.id, 'name': name, 'email': normalized, 'ip': ip})
        visit._send_code()
        return visit

    @api.model
    def _generate_code(self):
        return '%06d' % secrets.randbelow(10 ** 6)

    def _hash_code(self, code):
        return hashlib.sha256(('%s:%s' % (self.sudo().access_token, code)).encode()).hexdigest()

    def _check_token(self, token):
        self.ensure_one()
        return bool(token) and consteq(self.sudo().access_token or '', token)

    def _send_code(self):
        """ Email a new code to the visitor. :return: False when one was sent less than a minute ago, or too many """
        self.ensure_one()
        me = self.sudo()
        if me.request_id:
            return False
        now = fields.Datetime.now()
        if me.code_sends >= CODE_SENDS or (me.code_expiry and me.code_expiry - timedelta(minutes=CODE_MINUTES) >
                                           now - timedelta(seconds=CODE_RESEND_SECONDS)):
            return False
        code = self._generate_code()
        me.write({'code_hash': self._hash_code(code), 'code_attempts': 0, 'code_sends': me.code_sends + 1,
                  'code_expiry': now + timedelta(minutes=CODE_MINUTES)})
        template = me.template_id
        company = template.company_id or template._share_user().company_id
        body = self.env['ir.qweb']._render('om_sign.mail_sign_share_code', {
            'visit': me, 'template': template, 'company': company, 'code': code, 'minutes': CODE_MINUTES})
        self.env['mail.mail'].sudo().create({
            'subject': self.env._('Your code to sign %s', template.name),
            'email_from': company.email_formatted or template._share_user().email_formatted,
            'email_to': me.email,
            'body_html': body,
            'auto_delete': True,
        })
        return True

    # ------------------------------------------------------------------
    # The visitor enters the code
    # ------------------------------------------------------------------

    def _verify_code(self, code):
        """ :return: whether `code` is the one emailed, still valid """
        self.ensure_one()
        me = self.sudo()
        if me.request_id or not me.code_hash or me.code_attempts >= CODE_ATTEMPTS or \
                me.code_expiry < fields.Datetime.now():
            return False
        if not consteq(self._hash_code((code or '').strip()), me.code_hash):
            me.code_attempts += 1
            return False
        me.code_hash = False
        return True

    def _find_partner(self):
        """ :return: the contact of the visitor: the one of their email, else a new one """
        self.ensure_one()
        Partner = self.env['res.partner'].sudo()
        company = self.template_id.company_id
        partner = Partner.search([('email_normalized', '=', self.email),
                                  ('company_id', 'in', [False, *company.ids])], limit=1)
        return partner or Partner.create({'name': self.name, 'email': self.email})

    def _create_request(self):
        """ The visitor confirmed their email: the request of the template, the visitor signing as its role chosen
        when sending, sent as the user who shared the template, in the company of the template.

        :return: the signer of the visitor """
        self.ensure_one()
        visit = self.sudo()
        template = visit.template_id
        user = template._share_user()
        company = template.company_id or user.company_id
        # as the user sharing, who is the person sending; as the super user, the visitor being public
        env = self.env(user=user, su=True, context=dict(self.env.context, allowed_company_ids=company.ids))
        template = template.with_env(env)
        role = template.share_role_id
        partner = visit.with_env(env)._find_partner()
        partners = {each: partner if each == role else each._get_partner() for each in template.role_ids}
        missing = [each.name for each, signer in partners.items() if not signer.email]
        if missing:
            raise UserError(self.env._('This document cannot be signed from the link now: %s has no email.',
                                       ', '.join(missing)))
        sign_request = env['sign.request'].create(template._prepare_request(partners, **{
            **template._request_defaults(),
            'source': 'share_link',
            'requested_by_id': user.id,
            'company_id': company.id,
        }))
        signer = sign_request.signer_ids.filtered(lambda signer: signer.template_role_id == role)
        # the visitor confirmed their email already
        signer.write({'code_verified': True})
        visit.request_id = sign_request
        sign_request.action_send()
        sign_request.message_post(
            body=self.env._('Made from the shared link by %(name)s (%(email)s).', name=visit.name, email=visit.email),
            subtype_xmlid='mail.mt_note')
        return signer
