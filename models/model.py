import logging
from odoo import api, fields, models, _
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    def _remove_data(self, models_to_remove, sequences=None):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Only Administrators can perform this operation."))

        sequences = sequences or []

        for model_name in models_to_remove:
            try:
                model = self.env.get(model_name)
                if not model:
                    _logger.warning("Model not found: %s", model_name)
                    continue

                table_name = model._table
                sql = f'DELETE FROM "{table_name}"'

                self.env.cr.execute(sql)

            except Exception as e:
                _logger.warning('Remove data error for %s: %s', model_name, e)

        for seq_prefix in sequences:
            domain = ['|', ('code', '=ilike', seq_prefix + '%'), ('prefix', '=ilike', seq_prefix + '%')]
            try:
                seqs = self.env['ir.sequence'].sudo().search(domain)
                if seqs:
                    seqs.write({'number_next': 1})
            except Exception as e:
                _logger.warning('Reset sequence error for %s: %s', seq_prefix, e)

        return True