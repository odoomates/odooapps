import { _t } from "@web/core/l10n/translation";
import { user } from "@web/core/user";

export const WHATSAPP_GROUP = "om_whatsapp_base.group_om_whatsapp_user";

/**
 * Open the WhatsApp composer on records; ``number`` sends to that number
 * instead of the one found on the record.
 */
export function openWhatsappComposer(action, { resModel, resIds, number, onClose }) {
    return action.doAction(
        {
            type: "ir.actions.act_window",
            target: "new",
            name: _t("Send WhatsApp"),
            res_model: "om.whatsapp.composer",
            views: [[false, "form"]],
            context: {
                ...user.context,
                active_model: resModel,
                active_ids: resIds,
                active_id: resIds[0],
                ...(number ? { om_whatsapp_number: number } : {}),
            },
        },
        { onClose }
    );
}
