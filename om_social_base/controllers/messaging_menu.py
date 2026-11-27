from odoo.fields import Domain

from odoo.addons.mail.controllers.discuss.messaging_menu import DiscussMessagingMenuController

# the tab of the Social Inbox; its former name keeps working
TABS = ('om_social', 'om_whatsapp')


class OmSocialMessagingMenuController(DiscussMessagingMenuController):
    """ The Social Inbox tab of the messaging menu and of Discuss: the
    conversations of the user. """

    def _get_menu_tab_domain(self, tab_id):
        if tab_id not in TABS:
            return super()._get_menu_tab_domain(tab_id)
        return Domain([('channel_type', '=', 'om_social'), ('self_member_id.is_pinned', '=', True)])

    def _get_menu_tab_filter_domain(self, tab_id, filter_id):
        if tab_id in TABS and filter_id in ('om_social_unread', 'om_whatsapp_unread'):
            return Domain('self_member_id.is_unread', '=', True)
        return super()._get_menu_tab_filter_domain(tab_id, filter_id)
