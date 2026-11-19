import { Component, useListener, usePlugin, useProps } from "@odoo/owl";
import { BarcodePlugin } from "@barcodes/barcode_plugin";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

/**
 * Scan to add: on a form carrying this widget, a barcode scanned outside a text field adds the
 * product to the document, or raises its quantity. The document is saved first.
 */
export class QuickAddScanner extends Component {
    static template = "om_quick_add.Scanner";
    props = useProps({ ...standardWidgetProps });

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        // one scan after the other: a quick series of scans must not save the document twice at once
        this.queue = Promise.resolve();
        const barcode = usePlugin(BarcodePlugin);
        useListener(barcode.bus, "barcode_scanned", (ev) => {
            const code = ev.detail.barcode;
            this.queue = this.queue.then(() => this.add(code)).catch(() => {});
        });
    }

    async add(code) {
        const record = this.props.record;
        if (this.props.readonly || !record.data.om_quick_add_ok) {
            return;
        }
        // a dialog open over the form (Paste lines, a line...) takes the scans, not the document behind it
        if (!this.env.inDialog && document.querySelector(".o_dialog")) {
            return;
        }
        if (record.isNew || (await record.isDirty())) {
            if (!(await record.save())) {
                return;
            }
        }
        const result = await this.orm.call(record.resModel, "om_quick_add_scan", [[record.resId], code]);
        await record.load();
        this.notification.add(result.message, { type: result.type });
    }
}

registry.category("view_widgets").add("om_quick_add_scanner", { component: QuickAddScanner });
