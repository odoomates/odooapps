import { Component, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useFileViewer } from "@web/core/file_viewer/file_viewer_hook";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * An eye on a row of a list: the main attachment of the record (the scan of a vendor bill) opens in the file
 * viewer over the list, so the bills are checked against their document without opening each of them.
 */
export class AttachmentPreviewField extends Component {
    static template = "om_account_accountant.AttachmentPreviewField";
    props = useProps({ ...standardFieldProps });

    setup() {
        this.orm = useService("orm");
        this.store = useService("mail.store");
        this.fileViewer = useFileViewer();
    }

    get attachmentId() {
        return this.props.record.data[this.props.name]?.id;
    }

    async preview() {
        const [data] = await this.orm.read("ir.attachment", [this.attachmentId], ["name", "mimetype"]);
        if (!data) {
            return;
        }
        const attachment = this.store["ir.attachment"].insert({
            id: data.id,
            name: data.name,
            mimetype: data.mimetype,
        });
        this.fileViewer.open(attachment);
    }
}

export const attachmentPreviewField = {
    component: AttachmentPreviewField,
    displayName: _t("Attachment Preview"),
    supportedTypes: ["many2one"],
};

registry.category("fields").add("om_attachment_preview", attachmentPreviewField);
