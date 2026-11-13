from odoo import models


class Base(models.AbstractModel):
    _inherit = 'base'

    def _phone_get_recipients_info(self, force_field=False, partner_fallback=True):
        """ The number to send to for each record, and its customer:
        {record.id: {'partner', 'sanitized', 'number', 'partner_store',
        'field_store'}}. The number of the record itself first (``force_field``
        or its phone fields), else the one of its customer. """
        result = dict.fromkeys(self.ids, False)
        tocheck_fields = [force_field] if force_field else self._phone_get_number_fields()
        all_partners_by_record = self._mail_get_partners()
        for record in self:
            all_numbers = [record[fname] for fname in tocheck_fields if fname in record]
            all_partners = all_partners_by_record[record.id]

            valid_number, fname = False, False
            for fname in [f for f in tocheck_fields if f in record]:
                valid_number = record._phone_format(fname=fname)
                if valid_number:
                    break

            if valid_number:
                result[record.id] = {
                    'partner': all_partners[0] if all_partners else self.env['res.partner'],
                    'sanitized': valid_number,
                    'number': record[fname],
                    'partner_store': False,
                    'field_store': fname,
                }
            elif all_partners and partner_fallback:
                partner = self.env['res.partner']
                for partner in all_partners:
                    for fname in self.env['res.partner']._phone_get_number_fields():
                        valid_number = partner._phone_format(fname=fname)
                        if valid_number:
                            break
                    if valid_number:
                        break
                if not valid_number:
                    fname = 'phone'
                result[record.id] = {
                    'partner': partner,
                    'sanitized': valid_number or False,
                    'number': partner[fname],
                    'partner_store': True,
                    'field_store': fname,
                }
            else:
                # no valid number: the first number set, as it is
                value, fname = next(
                    ((value, fname) for value, fname in zip(all_numbers, tocheck_fields) if value),
                    (False, tocheck_fields[0] if tocheck_fields else False)
                )
                result[record.id] = {
                    'partner': self.env['res.partner'],
                    'sanitized': False,
                    'number': value,
                    'partner_store': False,
                    'field_store': fname,
                }
        return result
