/** @odoo-module **/

import { Component } from "@odoo/owl";
import { _lt } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * An eye on a row of a list: the main attachment of the record (the scan of a vendor bill) opens in a new tab of
 * the browser, so the bills are checked against their document without opening each of them.
 */
export class AttachmentPreviewField extends Component {
    get attachmentId() {
        // a many2one value is an [id, name] pair
        return this.props.value?.[0];
    }

    preview() {
        if (this.attachmentId) {
            window.open(`/web/content/${this.attachmentId}`, "_blank", "noopener");
        }
    }
}

AttachmentPreviewField.template = "om_account_accountant.AttachmentPreviewField";
AttachmentPreviewField.props = { ...standardFieldProps };
AttachmentPreviewField.displayName = _lt("Attachment Preview");
AttachmentPreviewField.supportedTypes = ["many2one"];

registry.category("fields").add("om_attachment_preview", AttachmentPreviewField);
