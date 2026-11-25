from odoo import api, models

# the (model, id, method) of the records whose approved button is about to run: the server check lets them through
# once, the approval being used up by the button
CLEARED = 'om_account_approval_cleared'


class ApprovalRequest(models.Model):
    _inherit = 'approval.request'

    def _consume(self, approved):
        """ The button of the web client, approved, is about to run: its records are let through by the server check. """
        self._om_clear(approved)
        return super()._consume(approved)

    def _run_button(self):
        """ The button run once approved is let through by the server check, for this run only. """
        keys = self._om_clear(self)
        try:
            return super()._run_button()
        finally:
            self.env.cr.cache.get(CLEARED, set()).difference_update(keys)

    @api.model
    def _om_clear(self, requests):
        keys = {(request.res_model, request.res_id, request.method) for request in requests if request.method}
        self.env.cr.cache.setdefault(CLEARED, set()).update(keys)
        return keys

    @api.model
    def _om_check_server(self, records, method):
        """ The approval flows of the button `method` applied to `records` posted by the server, whatever called it:
        a record whose request is approved goes on, the request being used up as by the button; a record let
        through by the button goes on.

        :return: the records still waiting for an approval, and the records unlocked here for the call
        """
        Rule = self.env['approval.rule']
        blocked = released = records.browse()
        if not records or not Rule._has_button_flows(records._name, method):
            return blocked, released
        cleared = self.env.cr.cache.setdefault(CLEARED, set())
        for record in records:
            key = (record._name, record.id, method)
            if key in cleared:
                cleared.discard(key)
                continue
            if not Rule._get_flow(record, method):
                continue
            approved = self.sudo().search([
                ('res_model', '=', record._name), ('res_id', '=', record.id), ('method', '=', method),
                ('state', '=', 'approved'),
            ], order='id desc', limit=1)
            if approved:
                self._consume(approved)
                cleared.discard(key)
                released |= record
                continue
            blocked |= record
        return blocked, released

    @api.model
    def _om_last_request(self, record, method):
        return self.sudo().search([
            ('res_model', '=', record._name), ('res_id', '=', record.id), ('method', '=', method),
        ], order='id desc', limit=1)

    @api.model
    def _om_blocked_message(self, records, method):
        """ :return: why `records` are not posted, one line each """
        lines = []
        for record in records:
            request = self._om_last_request(record, method)
            if request.state == 'to_approve':
                line = self.env._('%(record)s waits for the approval %(request)s (%(step)s).',
                                  record=record.display_name, request=request.name, step=request.approval_step)
            elif request.state == 'refused':
                line = self.env._('%(record)s: the approval %(request)s was refused.',
                                  record=record.display_name, request=request.name)
            else:
                line = self.env._('%s needs an approval: open it and click Post to ask for it.', record.display_name)
            lines.append(line)
        return self.env._('Not posted, an approval is missing:\n%s', '\n'.join(lines))
