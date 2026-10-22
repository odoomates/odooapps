import base64
import logging
import os
import secrets
import shutil
import subprocess
import time
from datetime import datetime, time as day_time
from pathlib import Path
from urllib.parse import urlparse

try:
    import resource
except ImportError:  # Windows
    resource = None

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import config

from odoo.addons.om_whatsapp_device.tools import BridgeError, WhatsappBridge

_logger = logging.getLogger(__name__)

WEBHOOK_PATH = '/om_whatsapp_device/webhook'
BRIDGE_DIR = Path(__file__).resolve().parent.parent / 'bridge'
DEFAULT_BRIDGE_URL = 'http://127.0.0.1:8077'
# what the WhatsApp Bridge says of a session, as the state of the account
BRIDGE_STATES = {
    'starting': 'connecting', 'connecting': 'connecting', 'reconnecting': 'connecting',
    'qr': 'linking', 'pairing': 'linking',
    'open': 'linked',
    'logged_out': 'logged_out',
    'stopped': 'draft',
    'error': 'error',
    'offline': 'offline',
}


def _lift_memory_limit():
    """ The bridge does not take the memory limit of Odoo (limit_memory_hard):
    its WebAssembly reserves more address space than that. """
    _soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (hard, hard))


class OmWhatsappAccount(models.Model):
    """ WhatsApp QR: the account is a linked device of a WhatsApp, as WhatsApp
    Web is, kept connected on the server by the WhatsApp Bridge of this
    module. The user scans a QR code in Odoo; then messages go out from the
    server, one at a time, with the pause of a person between two, up to a
    number a day. """
    _inherit = 'om.whatsapp.account'

    provider = fields.Selection(selection_add=[('device', 'WhatsApp QR (Linked Device)')], ondelete={'device': 'set default'})
    device_key = fields.Char('Session', readonly=True, copy=False, default=lambda self: secrets.token_urlsafe(18),
                             help="The name of the session of this account in the WhatsApp Bridge.")
    device_bridge_url = fields.Char(
        'WhatsApp Bridge', default=lambda self: self.env['ir.config_parameter'].sudo().get_str(
            'om_whatsapp_device.bridge_url') or DEFAULT_BRIDGE_URL,
        groups='base.group_system',
        help="Where the WhatsApp Bridge of this module runs: on this server, http://127.0.0.1:8077 by default.")
    device_state = fields.Selection([
        ('draft', 'Not Linked'),
        ('linking', 'Waiting for the Phone'),
        ('connecting', 'Connecting'),
        ('linked', 'Linked'),
        ('logged_out', 'Unlinked'),
        ('offline', 'Bridge Not Running'),
        ('error', 'Error'),
    ], string='WhatsApp', default='draft', readonly=True, copy=False)
    device_reason = fields.Char('Last Problem', readonly=True, copy=False)
    device_checked_on = fields.Datetime('Bridge Last Checked', readonly=True, copy=False)
    device_daily_limit = fields.Integer(
        'Messages a Day', default=200,
        help="At most this many messages a day from this number. WhatsApp bans the numbers that send too much from a "
             "linked device: raise it slowly.")
    device_min_gap = fields.Integer('Pause Between Messages (s)', default=3)
    device_max_gap = fields.Integer('Up To (s)', default=8,
                                    help="A random pause of a person between two messages.")
    device_secret = fields.Char('Secret of the Bridge', compute='_compute_device_secret',
                                groups='base.group_system')

    _device_key_unique = models.Constraint('unique (device_key)', 'A session is the session of one account.')

    @api.depends('provider')
    def _compute_capabilities(self):
        super()._compute_capabilities()
        for account in self.filtered(lambda a: a.provider == 'device'):
            account.can_send_files = True
            account.can_send_batch = True
            account.can_send_unattended = True

    def _compute_device_secret(self):
        self.device_secret = self._device_bridge_secret()

    @api.model
    def _device_bridge_secret(self):
        """ The secret shared with the WhatsApp Bridge: made on first use. """
        params = self.env['ir.config_parameter'].sudo()
        secret = params.get_str('om_whatsapp_device.secret')
        if not secret:
            secret = secrets.token_urlsafe(32)
            params.set_str('om_whatsapp_device.secret', secret)
        return secret

    def _device_bridge(self):
        self.ensure_one()
        return WhatsappBridge(self.sudo().device_bridge_url or DEFAULT_BRIDGE_URL, self._device_bridge_secret())

    def _device_webhook_url(self):
        """ The bridge runs on this server: it calls Odoo on this server,
        unless the system parameter om_whatsapp_device.odoo_url says where. """
        url = self.env['ir.config_parameter'].sudo().get_str('om_whatsapp_device.odoo_url')
        if not url:
            url = f"http://127.0.0.1:{config.get('http_port') or 8069}"
        return url.rstrip('/') + WEBHOOK_PATH

    def _device_check_manager(self):
        if not self.env.user.has_group('om_whatsapp_base.group_om_whatsapp_manager'):
            raise AccessError(_("Only a WhatsApp administrator links a number."))

    # ------------------------------------------------------------
    # LINKING
    # ------------------------------------------------------------

    def _device_start_session(self, **extra):
        """ Start the session in the bridge. Its state comes by the webhook:
        writing it here too would race with it. """
        self.ensure_one()
        return self._device_bridge().start(
            self.device_key,
            webhook_url=self._device_webhook_url(),
            database=self.env.cr.dbname,
            min_gap=max(self.device_min_gap, 0) * 1000,
            max_gap=max(self.device_max_gap, self.device_min_gap, 0) * 1000,
            **extra,
        )

    def action_device_link(self):
        """ The window that shows the QR code to scan, live. """
        self.ensure_one()
        self._device_check_manager()
        try:
            self._device_start_session(restart=self.device_state in ('logged_out', 'error'))
        except BridgeError as error:
            raise UserError(_("%(error)s\n\nClick Start the Bridge, or see the README of the module to run it as a service.",
                              error=error)) from error
        return {
            'type': 'ir.actions.client',
            'tag': 'om_whatsapp_device_link',
            'name': _("Link WhatsApp"),
            'target': 'new',
            'params': {'account_id': self.id},
        }

    def device_link_status(self):
        """ What the link window shows: the QR code, the pairing code, or
        linked. Asked every two seconds by the window. """
        self.ensure_one()
        self._device_check_manager()
        try:
            status = self._device_bridge().status(self.device_key)
        except BridgeError as error:
            self._device_write_state({'state': 'offline', 'reason': str(error)})
            return {'state': 'offline', 'reason': str(error)}
        self._device_write_state(status)
        return {
            'state': self.device_state,
            # an image the bridge draws: no drawing library needed on the server of Odoo
            'qr_image': status.get('qr_image') or False,
            'pairing_code': status.get('pairing_code'),
            'number': self.phone if self.device_state == 'linked' else False,
            'reason': status.get('reason'),
        }

    def device_link_with_code(self, phone):
        """ A pairing code to type on the phone, instead of the QR code. """
        self.ensure_one()
        self._device_check_manager()
        digits = ''.join(char for char in phone or '' if char.isdigit())
        if not 8 <= len(digits) <= 15:
            raise UserError(_("Give the number of the WhatsApp to link, with its country code."))
        try:
            self._device_start_session(pairing_phone=digits, restart=True)
        except BridgeError as error:
            raise UserError(str(error)) from error
        return self.device_link_status()

    def action_device_unlink(self):
        """ Unlink: the number leaves the linked devices of the phone. """
        self.ensure_one()
        self._device_check_manager()
        try:
            self._device_bridge().logout(self.device_key)
        except BridgeError as error:
            raise UserError(str(error)) from error
        self.sudo().write({'device_state': 'draft', 'device_reason': False})
        return True

    def _device_write_state(self, status, checked=False):
        """ The state of the session, as the bridge tells it: written only
        when it changed, as the webhook of the bridge writes it at the same
        time. ``checked`` notes the time of a check. """
        self.ensure_one()
        values = {'device_state': BRIDGE_STATES.get(status.get('state'), self.device_state),
                  'device_reason': status.get('reason') or False}
        if status.get('state') == 'open' and status.get('me'):
            values['phone'] = f"+{status['me']}"
        account = self.sudo()
        values = {name: value for name, value in values.items() if account[name] != value}
        if checked:
            values['device_checked_on'] = fields.Datetime.now()
        if values:
            account.write(values)

    # ------------------------------------------------------------
    # THE BRIDGE ON THIS SERVER
    # ------------------------------------------------------------

    @api.model
    def _device_bridge_paths(self):
        """ Node.js, and the folder of the bridge with its packages: what
        starting it needs, or what is missing. """
        node = self.env['ir.config_parameter'].sudo().get_str('om_whatsapp_device.node') or shutil.which('node')
        if not node:
            raise UserError(_("The WhatsApp Bridge runs on Node.js, version 20 or later: install it on the server "
                              "(e.g. sudo apt install nodejs npm), or give its path in the system parameter "
                              "om_whatsapp_device.node."))
        if not (BRIDGE_DIR / 'node_modules').is_dir():
            raise UserError(_("Install the packages of the WhatsApp Bridge once, on the server:\n\ncd %(folder)s && npm ci",
                              folder=BRIDGE_DIR))
        return node, BRIDGE_DIR

    def action_device_start_bridge(self):
        """ Start the WhatsApp Bridge on this server, from Odoo; it then starts
        again by itself when Odoo checks it. A service of the server (systemd,
        Docker) is sturdier: see the README of the module. """
        self.ensure_one()
        if not self.env.user._is_system():
            raise AccessError(_("Only an administrator of Odoo starts the WhatsApp Bridge."))
        self._device_start_bridge_process()
        self.env['ir.config_parameter'].sudo().set_bool('om_whatsapp_device.autostart', True)
        for _wait in range(20):
            try:
                self._device_bridge().health()
                break
            except BridgeError:
                time.sleep(0.5)
        else:
            raise UserError(_("The WhatsApp Bridge did not start: see its log, %(log)s.", log=self._device_bridge_log()))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'type': 'success', 'message': _("The WhatsApp Bridge runs: link the number."),
                       'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}},
        }

    @api.model
    def _device_bridge_log(self):
        return Path(config['data_dir']) / 'om_whatsapp_bridge' / 'bridge.log'

    def _device_start_bridge_process(self):
        self.ensure_one()
        node, folder = self._device_bridge_paths()
        url = urlparse(self.sudo().device_bridge_url or DEFAULT_BRIDGE_URL)
        if url.hostname not in ('127.0.0.1', 'localhost'):
            raise UserError(_("Odoo starts the WhatsApp Bridge of this server only: %(url)s is another one.",
                              url=url.geturl()))
        log = self._device_bridge_log()
        # the keys of the linked devices are in it: the other users of the server keep out
        log.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        log.parent.chmod(0o700)
        env = {
            **os.environ,
            'OM_WA_SECRET': self._device_bridge_secret(),
            'OM_WA_HOST': '127.0.0.1',
            'OM_WA_PORT': str(url.port or 8077),
            'OM_WA_DATA': str(log.parent / 'data'),
        }
        with log.open('ab') as output:
            subprocess.Popen([node, 'src/server.js'], cwd=folder, env=env, stdout=output, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, start_new_session=True,
                             preexec_fn=_lift_memory_limit if resource else None)
        _logger.info("WhatsApp Bridge started from Odoo on port %s", env['OM_WA_PORT'])

    @api.model
    def _cron_device_check(self):
        """ The state of the linked accounts; a bridge Odoo started that
        stopped (the server restarted) is started again. """
        accounts = self.search([('provider', '=', 'device'), ('device_state', '!=', 'draft')])
        if not accounts:
            return
        restarted = False
        for account in accounts:
            try:
                account._device_write_state(account._device_bridge().status(account.device_key), checked=True)
            except BridgeError as error:
                autostart = self.env['ir.config_parameter'].sudo().get_bool('om_whatsapp_device.autostart')
                if autostart and not restarted:
                    restarted = True
                    try:
                        account._device_start_bridge_process()
                        continue
                    except UserError as start_error:
                        error = start_error
                account.sudo().write({'device_state': 'offline', 'device_reason': str(error),
                                      'device_checked_on': fields.Datetime.now()})

    # ------------------------------------------------------------
    # SENDING
    # ------------------------------------------------------------

    def _om_whatsapp_send_device(self, notifications):
        """ One message a user sends goes at once; several wait in the queue,
        sent one at a time up to the number a day. """
        self.ensure_one()
        if len(notifications) > 1:
            return self._device_queue()
        if self._device_sent_today() >= self.device_daily_limit:
            notifications._om_whatsapp_set_status('failed', _(
                "%(account)s sent its %(count)s messages of the day: send it again tomorrow, or raise the number a day "
                "slowly.", account=self.name, count=self.device_daily_limit))
            return None
        self._device_send(notifications)
        return None

    def _om_whatsapp_send_automated(self, notifications):
        self.ensure_one()
        if self.provider != 'device':
            return super()._om_whatsapp_send_automated(notifications)
        return self._device_queue()

    def _device_queue(self):
        self.env.ref('om_whatsapp_device.ir_cron_device_send_queue')._trigger()
        return None

    def _device_sent_today(self):
        """ The messages that went out today: one per WhatsApp id, the copies of
        the conversations not counted twice. """
        self.ensure_one()
        start = datetime.combine(fields.Date.today(), day_time.min)
        notifications = self.env['mail.notification'].sudo().search([
            ('notification_type', '=', 'om_whatsapp'),
            ('notification_status', 'in', ('pending', 'sent')),
            ('mail_message_id.om_whatsapp_account_id', '=', self.id),
            ('mail_message_id.date', '>=', start),
        ])
        return len(set(notifications.mail_message_id.mapped(lambda m: m.om_whatsapp_id or m.id)))

    @api.model
    def _cron_device_send_queue(self, limit=200):
        """ Send the queued messages of the linked accounts, one at a time,
        up to the number a day of each: the others wait for tomorrow. """
        Notification = self.env['mail.notification'].sudo()
        queued = Notification.search([
            ('notification_type', '=', 'om_whatsapp'),
            ('notification_status', '=', 'ready'),
            ('mail_message_id.om_whatsapp_account_id.provider', '=', 'device'),
        ], order='id', limit=limit)
        for account in queued.mail_message_id.om_whatsapp_account_id:
            if account.device_state != 'linked':
                continue
            room = account.device_daily_limit - account._device_sent_today()
            for notification in queued.filtered(lambda n: n.mail_message_id.om_whatsapp_account_id == account)[:max(room, 0)]:
                account._device_send(notification)
                if self.env.context.get('cron_id'):
                    self.env['ir.cron']._commit_progress(1, remaining=0)

    def _om_whatsapp_picture_device(self, number):
        """ The profile picture of ``number``, read by the bridge: base64, or False. """
        self.ensure_one()
        if self.device_state != 'linked':
            return False
        return self._device_bridge().picture(self.device_key, number) or False

    def _om_whatsapp_receipt_device(self, number, whatsapp_ids, kind):
        self.ensure_one()
        if self.device_state != 'linked':
            raise UserError(_("%(account)s is not linked to WhatsApp: link it on the account.", account=self.name))
        try:
            self._device_bridge().receipt(self.device_key, number, whatsapp_ids, kind)
        except BridgeError as error:
            raise UserError(str(error)) from error
        return None

    def _om_whatsapp_react_device(self, number, message, emoji, from_me):
        """ A reaction goes at once, through the bridge: not one of the messages of the day. """
        self.ensure_one()
        if self.device_state != 'linked':
            raise UserError(_("%(account)s is not linked to WhatsApp: link it on the account.", account=self.name))
        try:
            self._device_bridge().react(self.device_key, number, message.om_whatsapp_id, from_me, emoji)
        except BridgeError as error:
            raise UserError(str(error)) from error
        return None

    def _device_send(self, notifications):
        self.ensure_one()
        if self.device_state != 'linked':
            notifications._om_whatsapp_set_status('failed', _(
                "%(account)s is not linked to WhatsApp: link it on the account.", account=self.name))
            return
        bridge = self._device_bridge()
        for notification in notifications:
            message = notification.mail_message_id.sudo()
            files = [{
                'name': attachment.name,
                'mimetype': attachment.mimetype,
                'data': base64.b64encode(attachment.raw or b'').decode(),
            } for attachment in message.attachment_ids]
            try:
                ids = bridge.send(self.device_key, notification.om_whatsapp_number, message._om_whatsapp_text(), files,
                                  quoted=message._om_whatsapp_quoted())
            except BridgeError as error:
                notification._om_whatsapp_set_status('failed', str(error))
                continue
            message.om_whatsapp_id = ids[0] if ids else False
            notification._om_whatsapp_set_status('sent')
