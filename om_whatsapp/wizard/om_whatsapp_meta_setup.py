import re
import secrets
from datetime import datetime

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.om_whatsapp.models.om_whatsapp_account import WEBHOOK_FIELDS
from odoo.addons.om_whatsapp.tools import MetaApi, MetaApiError

# the pages of Meta the assistant opens, for the app of the App ID once known
META_PAGES = {
    'business': 'https://business.facebook.com/overview',
    'create': 'https://developers.facebook.com/apps/creation/',
    'apps': 'https://developers.facebook.com/apps/',
    'basic': 'https://developers.facebook.com/apps/{app_id}/settings/basic/',
    'api_setup': 'https://developers.facebook.com/apps/{app_id}/whatsapp-business/wa-dev-console/',
    'system_users': 'https://business.facebook.com/settings/system-users',
    'explorer': 'https://developers.facebook.com/tools/explorer/',
}
PERMISSIONS = {'whatsapp_business_management', 'whatsapp_business_messaging'}
STEPS = ['app', 'app_id', 'secret', 'token', 'waba', 'number', 'done']
# the stages the stepper shows: the steps of the token all count as one
STAGES = [('app', ['app']), ('app_id', ['app_id']), ('secret', ['secret']), ('token', ['token', 'waba', 'number']),
          ('done', ['done'])]


class OmWhatsappMetaSetup(models.TransientModel):
    """ Connect an account to Meta, one task a page: create the app, paste its
    App ID, its App Secret, the token of its test page. Each value is checked
    at once; Odoo does the rest: the number, its registration, the webhook,
    a test message. The permanent token comes later, from the account. """
    _name = 'om.whatsapp.meta.setup'
    _description = 'Connect WhatsApp to Meta'

    account_id = fields.Many2one('om.whatsapp.account', required=True, ondelete='cascade')
    step = fields.Selection([
        ('app', 'Create the App'),
        ('app_id', 'App ID'),
        ('secret', 'App Secret'),
        ('token', 'Token'),
        ('waba', 'WhatsApp Account'),
        ('number', 'Number'),
        ('done', 'Done'),
        ('permanent', 'Permanent Token'),
        ('test', 'Test Message'),
    ], default='app', required=True)
    app_id = fields.Char('App ID')
    app_secret = fields.Char('App Secret', groups='om_whatsapp_base.group_om_whatsapp_manager')
    app_name = fields.Char('App', readonly=True)
    access_token = fields.Char('Access Token', groups='om_whatsapp_base.group_om_whatsapp_manager')
    waba_id = fields.Char('WhatsApp Business Account ID')
    number_ids = fields.One2many('om.whatsapp.meta.setup.number', 'setup_id', string='Numbers Found')
    number_id = fields.Many2one('om.whatsapp.meta.setup.number', string='Number', domain="[('setup_id', '=', id)]")
    test_number = fields.Char('Your WhatsApp Number', default=lambda self: self.env.user.partner_id.phone,
                              help="A test message goes to it. With the test number of Meta, it must be in the list of "
                                   "recipients of the app (the To field of its API Setup page).")
    report = fields.Html('Result', readonly=True, sanitize=False)
    progress = fields.Html(compute='_compute_progress', sanitize=False)
    # what Meta says of each value, as soon as it is pasted
    app_id_check = fields.Html(readonly=True, sanitize=False)
    secret_check = fields.Html(readonly=True, sanitize=False)
    token_check = fields.Html(readonly=True, sanitize=False)
    has_problems = fields.Boolean(readonly=True)
    # links to the pages of Meta: links, not buttons, so that nothing is saved nor checked to open them
    link_business = fields.Char(compute='_compute_links')
    link_create = fields.Char(compute='_compute_links')
    link_apps = fields.Char(compute='_compute_links')
    link_basic = fields.Char(compute='_compute_links')
    link_api_setup = fields.Char(compute='_compute_links')
    link_explorer = fields.Char(compute='_compute_links')
    link_system_users = fields.Char(compute='_compute_links')

    @api.depends('step')
    def _compute_progress(self):
        labels = dict(self._fields['step']._description_selection(self.env))
        labels.update(app=_("Your App"), token=_("Token"), done=_("Connected"))
        for setup in self:
            current = next((index for index, (_stage, steps) in enumerate(STAGES) if setup.step in steps), None)
            if current is None:
                setup.progress = False
                continue
            items = []
            for index, (stage, _steps) in enumerate(STAGES):
                state = 'done' if index < current or setup.step == 'done' else 'current' if index == current else 'todo'
                items.append(Markup(
                    '<li class="o_om_whatsapp_stepper_%s"><span class="o_om_whatsapp_stepper_dot">%s</span>'
                    '<span class="o_om_whatsapp_stepper_label">%s</span></li>') % (
                    state, '✓' if state == 'done' else index + 1, labels[stage]))
            setup.progress = Markup('<ol class="o_om_whatsapp_stepper">%s</ol>') % Markup().join(items)

    @staticmethod
    def _check_html(ok, message):
        return Markup('<span class="%s">%s %s</span>') % ('text-success' if ok else 'text-danger', '✓' if ok else '✗',
                                                         message)

    @api.onchange('app_id')
    def _onchange_app_id(self):
        app_id = re.sub(r'\D', '', self.app_id or '')
        if not self.app_id:
            self.app_id_check = False
        elif 10 <= len(app_id) <= 20:
            self.app_id_check = self._check_html(True, _("Looks like an App ID."))
        else:
            self.app_id_check = self._check_html(
                False, _("An App ID is a number of 15 digits or so, at the top of the page of your app."))

    @api.onchange('app_secret')
    def _onchange_app_secret(self):
        """ Meta answers with the name of the app: the App ID and the App
        Secret go together. """
        if not (self.app_secret or '').strip() or not self.app_id:
            self.secret_check = False
            return
        try:
            app = self._api().get_app()
        except MetaApiError:
            self.secret_check = self._check_html(
                False, _("Meta does not know this App Secret with this App ID: copy it again, from the same app."))
            return
        self.app_name = app.get('name')
        self.secret_check = self._check_html(True, _("App %(app)s found.", app=app.get('name')))

    @api.onchange('access_token')
    def _onchange_access_token(self):
        """ The checks of Connect, told at once: valid, for this app, with
        both permissions. """
        if not (self.access_token or '').strip() or not self.app_id or not self.app_secret:
            self.token_check = False
            return
        try:
            token = self._check_token()
        except UserError as error:
            self.token_check = self._check_html(False, error.args[0])
            return
        expiry = self._token_expiry(token)
        hours = expiry and max(int((expiry - datetime.now()).total_seconds() // 3600), 0)
        self.token_check = self._check_html(True, _(
            "Valid, with both permissions; it works %(hours)s more hours.", hours=hours) if expiry else _(
            "Valid, with both permissions; it never expires."))

    @api.depends('app_id')
    def _compute_links(self):
        for setup in self:
            app_id = re.sub(r'\D', '', setup.app_id or '')
            for page, url in META_PAGES.items():
                if '{app_id}' in url:
                    url = url.format(app_id=app_id) if app_id else META_PAGES['apps']
                setup[f'link_{page}'] = url

    @api.model
    def default_get(self, fields):
        values = super().default_get(fields)
        if account_id := values.get('account_id'):
            # default_get is open to anyone: the secret only goes to who may change the account
            account = self.env['om.whatsapp.account'].browse(account_id)
            self._check_account(account)
            account = account.sudo()
            values.update(app_id=account.meta_app_id, app_secret=account.meta_app_secret)
        return values

    def _check_account(self, account):
        if not self.env.user.has_group('om_whatsapp_base.group_om_whatsapp_manager'):
            raise AccessError(_("Only WhatsApp managers connect accounts to Meta."))
        account.check_access_rights('write')
        account.check_access_rule('write')

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'views': [(False, 'form')],
            'target': 'new',
            'name': _("Make the Connection Permanent") if self.step == 'permanent' else _("Connect to Meta"),
            'context': {'dialog_size': 'extra-large'} if self.step in STEPS else {},
        }

    def _go(self, step):
        self.step = step
        return self._reopen()

    def _api(self):
        self.ensure_one()
        return MetaApi(self.env, access_token=(self.access_token or '').strip(), app_id=(self.app_id or '').strip(),
                       app_secret=(self.app_secret or '').strip())

    def action_back(self):
        self.ensure_one()
        previous = STEPS[max(STEPS.index(self.step) - 1, 0)]
        if previous == 'waba' and not self.waba_id:
            previous = 'token'
        return self._go(previous)

    # ------------------------------------------------------------
    # ONE TASK A PAGE
    # ------------------------------------------------------------

    def action_app_created(self):
        return self._go('app_id')

    def action_check_app_id(self):
        self.ensure_one()
        self.app_id = re.sub(r'\D', '', self.app_id or '')
        if not 10 <= len(self.app_id) <= 20:
            raise UserError(_("An App ID is a number of 15 digits or so, at the top of the page of your app in Meta."))
        self._keep({'meta_app_id': self.app_id})
        return self._go('secret')

    def action_check_secret(self):
        """ Meta answers with the name of the app: the App ID and the App
        Secret go together. """
        self.ensure_one()
        self.app_secret = (self.app_secret or '').strip()
        if not self.app_secret:
            raise UserError(_("Paste the App Secret, copied from the settings of your app."))
        try:
            app = self._api().get_app()
        except MetaApiError as error:
            raise UserError(_("Meta does not know this App Secret with this App ID: copy the App Secret again (Show, "
                              "then copy), from the same app.\n\nMeta says: %(error)s", error=error)) from error
        self.app_name = app.get('name')
        self._keep({'meta_app_secret': self.app_secret})
        return self._go('token')

    def _keep(self, values):
        """ The values checked so far, on an account not connected yet: the
        assistant starts again from them. A connected account keeps its app
        until Connect: its webhook is signed with its App Secret. """
        self._check_account(self.account_id)
        account = self.account_id.sudo()
        if account.meta_state != 'connected':
            account.write(values)

    def action_make_permanent(self):
        self.ensure_one()
        return self.account_id.action_meta_permanent_token()

    def action_check_token(self):
        """ The token, then the numbers it may use: with one, Odoo connects at
        once. """
        self.ensure_one()
        self.account_id.check_access_rights('write')
        self.account_id.check_access_rule('write')
        self.access_token = (self.access_token or '').strip()
        if not self._waba_ids(self._check_token()):
            return self._go('waba')
        self.waba_id = False
        self._find_numbers()
        return self._numbers_found()

    def action_check_waba(self):
        """ The WhatsApp account the token did not name, given by hand. """
        self.ensure_one()
        self.account_id.check_access_rights('write')
        self.account_id.check_access_rule('write')
        self.waba_id = re.sub(r'\D', '', self.waba_id or '')
        if not self.waba_id:
            raise UserError(_("Copy the WhatsApp Business Account ID from the API Setup page of your app."))
        self._find_numbers()
        return self._numbers_found()

    def _numbers_found(self):
        if len(self.number_ids) == 1:
            return self.action_connect()
        return self._go('number')

    def _check_token(self):
        """ What Meta says of the token, refused with what to do. """
        self.ensure_one()
        if not self.access_token:
            raise UserError(_("Paste the token copied from the page of Meta."))
        api = self._api()
        try:
            token = api.debug_token()
        except MetaApiError as error:
            # the usual one: the token of another app, the Meta App of the Graph API Explorer left on it
            try:
                token_app = api.get_token_app()
            except MetaApiError:
                token_app = {}
            if token_app.get('id') and token_app['id'] != api.app_id:
                raise UserError(_("This token was made for the app %(token_app)s, not for your app %(app)s: in the "
                                  "Graph API Explorer, choose %(app)s as Meta App, then generate the token again.",
                                  token_app=token_app.get('name') or token_app['id'],
                                  app=self.app_name or api.app_id)) from error
            raise UserError(_("Meta says: %(error)s", error=error)) from error
        if not token.get('is_valid'):
            raise UserError(_("Meta says this token is not valid any more: a temporary token lasts 24 hours. Make a new "
                              "one on the page of Meta, and paste it again."))
        missing = PERMISSIONS - set(token.get('scopes') or [])
        if missing:
            raise UserError(_("This token lacks the permissions %(permissions)s: tick them when you make it.",
                              permissions=', '.join(sorted(missing))))
        return token

    @staticmethod
    def _token_expiry(token):
        """ When the token stops working: False when never. """
        expires = token.get('expires_at') or 0
        return datetime.fromtimestamp(expires) if expires else False

    @staticmethod
    def _waba_ids(token):
        """ The WhatsApp accounts the token names: none when it is not
        limited to some (Meta then gives no target_ids), and no call of the
        WhatsApp permissions lists them. """
        return [
            target for scope in token.get('granular_scopes') or []
            if scope.get('scope') == 'whatsapp_business_management'
            for target in scope.get('target_ids') or []
        ]

    def _find_numbers(self):
        """ The numbers of the WhatsApp accounts of the token, else of the
        one given. """
        token = self._check_token()
        api = self._api()
        waba_ids = self._waba_ids(token) or [self.waba_id]
        lines = []
        try:
            for waba_id in dict.fromkeys(waba_ids):
                waba = api.get_business_account(waba_id)
                for number in api.get_phone_numbers(waba_id):
                    lines.append({
                        'waba_id': waba_id,
                        'waba_name': waba.get('name'),
                        'phone_number_id': number.get('id'),
                        'display_phone_number': number.get('display_phone_number'),
                        'verified_name': number.get('verified_name'),
                        'quality_rating': number.get('quality_rating'),
                        'messaging_limit': number.get('messaging_limit_tier'),
                        'verification_status': number.get('code_verification_status'),
                    })
        except MetaApiError as error:
            if self.waba_id:
                raise UserError(_("Meta finds no WhatsApp account %(waba)s for this token: copy the WhatsApp Business "
                                  "Account ID again from the API Setup page of the same app.\n\nMeta says: %(error)s",
                                  waba=self.waba_id, error=error)) from error
            raise UserError(_("Meta says: %(error)s", error=error)) from error
        if not lines:
            raise UserError(_("The WhatsApp account has no number yet: Meta gives a test number on the API Setup page of "
                              "the app; your own number is added in WhatsApp Manager."))
        self.number_ids = [fields.Command.clear()] + [fields.Command.create(line) for line in lines]
        self.number_id = self.number_ids[:1]

    # ------------------------------------------------------------
    # CONNECT: THE REST BY ITSELF
    # ------------------------------------------------------------

    def action_connect(self):
        """ Save the app and the number on the account, register the number,
        set the webhook, send a test message: each step is told, done or what
        is missing. """
        self.ensure_one()
        if not self.number_id:
            raise UserError(_("Choose the number to send from."))
        token = self._check_token()
        self._check_account(self.account_id)
        account = self.account_id.sudo()
        number = self.number_id
        account._meta_take_number(number.phone_number_id, number.display_phone_number)
        account.write({
            'provider': 'meta',
            'meta_app_id': self.app_id.strip(),
            'meta_app_secret': self.app_secret.strip(),
            'meta_access_token': self.access_token.strip(),
            'meta_token_expires': self._token_expiry(token),
            'meta_waba_id': number.waba_id,
            'meta_waba_name': number.waba_name,
            'meta_phone_number_id': number.phone_number_id,
            'meta_verified_name': number.verified_name,
            'meta_quality_rating': number.quality_rating,
            'meta_messaging_limit': number.messaging_limit,
            'phone': number.display_phone_number,
            'meta_pin': account.meta_pin or ''.join(secrets.choice('0123456789') for _i in range(6)),
        })
        api = account._meta_api()
        steps = []

        def step(label, run, blocking=True):
            try:
                steps.append(('ok', label, run()))
            except MetaApiError as error:
                steps.append(('fail' if blocking else 'warn', label,
                              _("Meta says: %(error)s", error=account._meta_explain(error))))

        def register():
            api.register_phone_number(number.phone_number_id, account.meta_pin)
            return _("Two-step verification PIN %(pin)s: keep it, Meta asks for it to move the number.",
                              pin=account.meta_pin)

        def webhook():
            api.subscribe_app(number.waba_id)
            if not account._meta_webhook_reachable():
                raise MetaApiError(account._meta_unreachable_message())
            if not account._meta_database_reachable():
                raise MetaApiError(account._meta_database_message())
            api.set_webhook(account.meta_webhook_url, account.meta_verify_token, WEBHOOK_FIELDS)
            return account.meta_webhook_url

        def test_message():
            if not self.test_number:
                return _("No number given: none sent.")
            account._meta_send_template(self.test_number, 'hello_world')
            return _("To %(number)s: reply to it, the reply comes to Odoo.", number=self.test_number)

        # a number registered before (the test number of Meta, another tool) is refused: the test message tells
        step(_("Number registered for the Cloud API"), register, blocking=False)
        step(_("Messages of WhatsApp sent to this Odoo"), webhook)
        step(_("Test message sent"), test_message)
        problems = [f'{label}: {note}' for status, label, note in steps if status == 'fail']
        account.write({
            'meta_state': 'error' if problems else 'connected',
            'meta_status_message': '\n'.join(problems) or False,
            'meta_checked_on': fields.Datetime.now(),
        })
        self.write({'step': 'done', 'report': self._report(steps), 'has_problems': bool(problems)})
        return self._reopen()

    def action_send_test(self):
        """ The hello_world template of Meta to a number: the first message
        Meta lets a business send. """
        self.ensure_one()
        if not self.test_number:
            raise UserError(_("Give the number to send the test message to."))
        self._check_account(self.account_id)
        account = self.account_id.sudo()
        try:
            account._meta_send_template(self.test_number, 'hello_world')
        except MetaApiError as error:
            raise UserError(_("Meta says: %(error)s", error=account._meta_explain(error))) from error
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _("Test message sent to %(number)s: reply to it, the reply comes to the WhatsApp tab of Odoo.",
                             number=self.test_number),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def _report(self, steps):
        """ What Connect did: the number, as Meta sees it, then each step,
        done or what to do. """
        account = self.account_id.sudo()
        marks = {'ok': ('text-success', '✓'), 'warn': ('text-warning', '!'), 'fail': ('text-danger', '✗')}
        rows = Markup('').join(
            Markup('<li class="mb-2"><span class="%s fw-bold">%s</span> %s<br/><span class="text-muted">%s</span></li>') % (
                *marks[status], label, note or '')
            for status, label, note in steps
        )
        facts = [
            (_("Quality"), account.meta_quality_rating),
            (_("Daily limit"), account.meta_messaging_limit),
            (_("Token"), _(
                "works %(hours)s more hours",
                hours=max(int((account.meta_token_expires - fields.Datetime.now()).total_seconds() // 3600), 0))
             if account.meta_token_expires else _("never expires")),
        ]
        chips = Markup('').join(
            Markup('<span class="o_om_whatsapp_chip">%s: <b>%s</b></span>') % (label, value)
            for label, value in facts if value
        )
        return Markup(
            '<div class="o_om_whatsapp_summary"><div class="o_om_whatsapp_summary_number">%s</div>'
            '<div class="text-muted mb-2">%s</div><div class="mb-3">%s</div>'
            '<ul class="list-unstyled mb-0">%s</ul></div>') % (
            account.phone or account.meta_phone_number_id or '', account.meta_verified_name or account.meta_waba_name or '',
            chips, rows)

    # ------------------------------------------------------------
    # LATER: THE PERMANENT TOKEN
    # ------------------------------------------------------------

    def action_save_permanent(self):
        """ The token of a system user, which never expires, for the same
        WhatsApp account. """
        self.ensure_one()
        self.access_token = (self.access_token or '').strip()
        token = self._check_token()
        self._check_account(self.account_id)
        account = self.account_id.sudo()
        if token.get('expires_at'):
            raise UserError(_("This token expires: when you make it, choose the expiration Never."))
        waba_ids = self._waba_ids(token)
        if not waba_ids:
            # a token not limited to some accounts: Meta tells by answering
            try:
                self._api().get_business_account(account.meta_waba_id)
            except MetaApiError:
                waba_ids = None
            else:
                waba_ids = [account.meta_waba_id]
        if not waba_ids or account.meta_waba_id not in waba_ids:
            raise UserError(_("This token does not reach the WhatsApp account %(account)s: give it to the system user "
                              "(Assign assets), then make the token again.",
                              account=account.meta_waba_name or account.meta_waba_id))
        account.write({'meta_access_token': self.access_token, 'meta_token_expires': False})
        account._meta_check()
        return {'type': 'ir.actions.act_window_close'}


class OmWhatsappMetaSetupNumber(models.TransientModel):
    _name = 'om.whatsapp.meta.setup.number'
    _description = 'Number found in Meta'
    _rec_name = 'display_phone_number'

    setup_id = fields.Many2one('om.whatsapp.meta.setup', required=True, ondelete='cascade')
    waba_id = fields.Char('Business Account ID')
    waba_name = fields.Char('Business Account')
    phone_number_id = fields.Char('Phone Number ID')
    display_phone_number = fields.Char('Number')
    verified_name = fields.Char('Name in WhatsApp')
    quality_rating = fields.Char('Quality')
    messaging_limit = fields.Char('Limit')
    verification_status = fields.Char('Verification')

    @api.depends('display_phone_number', 'verified_name')
    def _compute_display_name(self):
        for number in self:
            number.display_name = f'{number.display_phone_number} ({number.verified_name})' if number.verified_name \
                else number.display_phone_number
