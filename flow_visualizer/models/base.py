# The events of a traced call: the records every model creates, edits and
# deletes, handed to the tracer of the call. Nothing happens when no call is
# traced.
from odoo import api, models

from .tracer import CURRENT


class Base(models.AbstractModel):
    _inherit = 'base'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        tracer = CURRENT.get()
        if tracer is not None and records:
            tracer.created(records)
        return records

    def write(self, vals):
        tracer = CURRENT.get()
        if tracer is None or not self:
            return super().write(vals)
        names = tracer.written_fields(self, vals)
        before = tracer.values(self, names)
        result = super().write(vals)
        tracer.written(self, names, before)
        return result

    def unlink(self):
        tracer = CURRENT.get()
        if tracer is not None and self:
            tracer.deleting(self)
        return super().unlink()
