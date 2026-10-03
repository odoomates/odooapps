from odoo import fields, models


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    # in the base module of Odoo 19: the same field, so that an upgrade keeps the numbers
    clearing_number = fields.Char(
        'Clearing Number',
        help="Routing number of the bank (United States), or institution and transit number (Canada): printed in "
             "the MICR line of the cheques.")

    def _om_check_routing_number(self):
        """ :return: the routing number printed in the MICR line, the ABA routing number of the US
                     localization when no clearing number is set """
        self.ensure_one()
        return self.clearing_number or ('aba_routing' in self._fields and self.aba_routing) or False
