from odoo.http import request

from odoo.addons.im_livechat.controllers.webclient import WebClient


class OmAiLivechatWebClient(WebClient):

    @classmethod
    def _store_init_livechat_fields(cls, res, params):
        result = super()._store_init_livechat_fields(res, params)
        # sudo - im_livechat.channel: the visitor may know whether the chat is answered
        channel = request.env['im_livechat.channel'].sudo().search([('id', '=', params)]) if params else None
        if not channel or not channel.om_ai_agent_id.active:
            return result
        country_id = (
            # sudo - res.country: reading the country of the visitor is allowed
            request.env['res.country'].sudo().search([('code', '=', code)]).id
            if (code := request.geoip.country_code) else None
        )
        url = request.httprequest.headers.get('Referer')
        # sudo - im_livechat.channel.rule: reading the rules of the channel is allowed
        rule = request.env['im_livechat.channel.rule'].sudo().match_rule(params, url, country_id)
        if rule.action != 'hide_button':
            # the AI agent answers when no operator is online
            res.attr('livechat_available', True)
        return result
