import { Component, useProps } from "@odoo/owl";
import { useFileViewer } from "@web/core/file_viewer/file_viewer_hook";
import { FileModel } from "@web/core/file_viewer/file_model";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

/**
 * The file of a document shown in its form: the image, the PDF, the video or the text, and a button opening it
 * full screen in the file viewer.
 */
export class DocumentsPreview extends Component {
    static template = "om_documents.DocumentsPreview";
    props = useProps({ ...standardWidgetProps });

    setup() {
        this.fileViewer = useFileViewer();
    }

    get file() {
        const data = this.props.record.data;
        if (data.type === "url" && data.url) {
            return Object.assign(new FileModel(), { id: this.props.record.resId, type: "url", url: data.url,
                name: data.name });
        }
        const attachment = data.attachment_id;
        const id = attachment && (attachment.id || attachment[0]);
        if (!id) {
            return null;
        }
        return Object.assign(new FileModel(), {
            id,
            name: data.file_name || data.name,
            mimetype: data.mimetype,
            checksum: data.checksum,
            type: "binary",
        });
    }

    openViewer() {
        const file = this.file;
        if (file?.isViewable) {
            this.fileViewer.open(file);
        }
    }
}

registry.category("view_widgets").add("om_documents_preview", { component: DocumentsPreview });
