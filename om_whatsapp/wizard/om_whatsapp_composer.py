from odoo import api, fields, models


class OmWhatsappComposer(models.TransientModel):
    """ From a Meta account, an approved template goes as Meta approved it,
    and free text only within 24 hours of the last message of the number. """
    _inherit = 'om.whatsapp.composer'

    meta_template_ready = fields.Boolean(compute='_compute_meta_template_ready')

    @api.depends('account_id', 'template_id')
    def _compute_meta_template_ready(self):
        for composer in self:
            composer.meta_template_ready = bool(
                composer.account_id.provider == 'meta' and composer.template_id
                and composer.template_id._meta_ready(composer.account_id))

    def action_send(self):
        self.ensure_one()
        if self.account_id.provider == 'meta' and not self.meta_template_ready and self.res_count == 1 and self.number:
            records = self._get_records()
            self.account_id._meta_check_window(records._phone_format(number=self.number) or self.number)
        return super().action_send()
