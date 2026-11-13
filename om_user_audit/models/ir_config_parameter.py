# Typed reads and writes of the system parameters, as Odoo 20 offers them, so
# that the code of this module stays the same on every version.
from odoo import api, models

TRUE = frozenset({'1', 'true', 'yes', 'on'})
FALSE = frozenset({'0', 'false', 'no', 'off', ''})


class IrConfigParameter(models.Model):
    _inherit = 'ir.config_parameter'

    @api.model
    def get_str(self, key, default=''):
        value = self.get_param(key)
        return default if value is False or value is None else value

    @api.model
    def get_int(self, key, default=0):
        value = self.get_param(key)
        if value is False or value is None or isinstance(value, bool):
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @api.model
    def get_bool(self, key, default=False):
        value = self.get_param(key)
        if value is False or value is None:
            return default
        value = str(value).strip().lower()
        if value in TRUE:
            return True
        return False if value in FALSE else default

    @api.model
    def set_str(self, key, value):
        return self.set_param(key, value)

    @api.model
    def set_int(self, key, value):
        return self.set_param(key, str(int(value)))

    @api.model
    def set_bool(self, key, value):
        return self.set_param(key, 'True' if value else 'False')
