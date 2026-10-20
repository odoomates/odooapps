from odoo.fields import Domain

from odoo.addons.mail.controllers.discuss.messaging_menu import DiscussMessagingMenuController


class OmWhatsappMessagingMenuController(DiscussMessagingMenuController):
    """ The WhatsApp tab of the messaging menu and of Discuss: the WhatsApp
    conversations of the user. """

    def _get_menu_tab_domain(self, tab_id):
        if tab_id != 'om_whatsapp':
            return super()._get_menu_tab_domain(tab_id)
        return Domain([('channel_type', '=', 'om_whatsapp'), ('self_member_id.is_pinned', '=', True)])

    def _get_menu_tab_filter_domain(self, tab_id, filter_id):
        if (tab_id, filter_id) == ('om_whatsapp', 'om_whatsapp_unread'):
            return Domain('self_member_id.is_unread', '=', True)
        return super()._get_menu_tab_filter_domain(tab_id, filter_id)
