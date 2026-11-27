import io
import logging

from PIL import Image

from odoo import fields, models

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def action_send_receipt_om_whatsapp(self, phone):
        """ Send the receipt of the order by WhatsApp to ``phone``, from the
        send receipt dialog: the receipt as a picture, with the invoice PDF
        when the order is invoiced, for the providers that send files. The
        message is kept on the order. Never raises: the cashier is told why
        it could not go.

        :return: {'url': link to open} for Click to Chat, {'error': reason}
            when it was not sent, else {}
        """
        self.ensure_one()
        config = self.config_id
        template = config.om_whatsapp_receipt_template_id or self.env.ref(
            'om_whatsapp_pos.om_whatsapp_template_pos_receipt', raise_if_not_found=False)
        account = config.om_whatsapp_account_id or template.account_id or \
            self.env['om.social.account']._get_default_account('whatsapp')
        if not config.om_whatsapp_receipt or not template:
            return {'error': self.env._("WhatsApp receipts are not set up on this point of sale.")}
        if not account:
            return {'error': self.env._("Choose the WhatsApp account of this point of sale in its settings.")}
        if not phone:
            return {'error': self.env._("Type the WhatsApp number of the customer.")}
        try:
            with self.env.cr.savepoint():
                return self.sudo()._om_whatsapp_send_receipt(phone, template.sudo(), account.sudo())
        except Exception as error:  # noqa: BLE001 - a receipt never stops the sale
            _logger.exception("WhatsApp receipt of %s not sent", self.name)
            return {'error': str(error)}

    def _om_whatsapp_receipt_pdf(self):
        """ The receipt the POS prints, as a one-page PDF. """
        self.ensure_one()
        image = Image.open(io.BytesIO(self.order_receipt_generate_image())).convert('RGB')
        stream = io.BytesIO()
        image.save(stream, 'PDF', resolution=150)
        return stream.getvalue()

    def _om_whatsapp_receipt_attachments(self):
        self.ensure_one()
        ticket = self.order_receipt_generate_image()
        commands = self._get_mail_attachments(self.name, ticket, None)
        return [command[1] for command in commands]

    def _om_whatsapp_send_receipt(self, phone, template, account):
        self.ensure_one()
        number = self._phone_format(number=phone, force_format='E164') or phone
        # Meta sends files after the 24 hours of the last message of the
        # customer only at the top of an approved template: there the receipt
        # goes as the PDF report of the template, else as a picture
        meta = account.provider == 'meta'
        attachment_ids = self._om_whatsapp_receipt_attachments() if account.can_send_files and not meta else []
        composer = self.env['om.whatsapp.composer'].with_context(
            active_model=self._name, active_ids=self.ids, active_id=self.id,
        ).create({
            'account_id': account.id,
            'template_id': template.id,
            'number': number,
            'partner_id': self.partner_id.id,
            'attachment_ids': [fields.Command.set(attachment_ids)],
            'attach_report': meta and account.can_send_files,
        })
        notifications = composer._post_messages(self)._om_social_notifications()
        queued = notifications.filtered(lambda n: n.notification_status == 'ready')
        if queued:
            if account.provider == 'link':
                action = queued._om_social_send()
                return {'url': action['url']} if action else {}
            account._om_social_send_automated(queued)
        failed = notifications.filtered(lambda n: n.notification_status in ('exception', 'canceled'))
        if failed:
            return {'error': failed[:1].failure_reason or self.env._("The number is opted out of WhatsApp.")}
        return {}
