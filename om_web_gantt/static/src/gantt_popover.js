import { Component, t, useProps } from "@odoo/owl";

import { _t } from "@web/core/l10n/translation";
import { formatDate, formatDateTime } from "@web/core/l10n/dates";
import { escapeXml as escape } from "./gantt_helpers";
import { parseXML } from "@web/core/utils/xml";
import { CARD_ATTRIBUTE } from "@web/views/card/card_arch_parser";
import { CardPopover } from "@web/views/card/card_popover/card_popover";

export class GanttPopover extends Component {
    static template = "om_web_gantt.GanttPopover";
    static components = { CardPopover };

    props = useProps({
        close: t.function(),
        model: t.object(),
        record: t.object(),
        openRecord: t.function(),
        deleteRecord: t.function(),
    });

    get cardPopoverProps() {
        const { model, record } = this.props;
        return {
            close: this.props.close,
            fields: model.fields,
            resModel: model.resModel,
            resId: record.id,
            popoverNode: model.archInfo.popoverNode,
            readonly: !model.canWrite,
            rootClass: `o_gantt_popover o_gantt_color_${record.colorIndex}`,
            context: model.meta.context,
            reloadOnClose: () => model.load(),
            openRecord: () => this.onEdit(),
            getDefaultPopoverBody: () => this.getDefaultPopoverBody(),
        };
    }

    get canEdit() {
        return this.props.model.canWrite;
    }

    get canDelete() {
        return this.props.model.canDelete;
    }

    formatPeriod() {
        const { model, record } = this.props;
        if (model.dateOnly) {
            const lastDay = record.stop.minus({ days: 1 });
            if (lastDay <= record.start) {
                return formatDate(record.start);
            }
            return `${formatDate(record.start)} - ${formatDate(lastDay)}`;
        }
        return `${formatDateTime(record.start)} - ${formatDateTime(record.stop)}`;
    }

    getDefaultPopoverBody() {
        const items = [
            `<div class="d-flex gap-2">
                <i class="oi oi-fw text-muted lh-base" data-icon="calendar_today" title="${escape(_t("Dates"))}"/>
                <span class="fw-bold">${escape(this.formatPeriod())}</span>
            </div>`,
        ];
        for (const fieldNode of Object.values(this.props.model.archInfo.popoverFieldNodes)) {
            if (["1", "True"].includes(fieldNode.invisible)) {
                items.push(`<field name="${fieldNode.name}" invisible="1"/>`);
                continue;
            }
            const widget = fieldNode.widget ? `widget="${fieldNode.widget}"` : "";
            const options = `options="${escape(JSON.stringify(fieldNode.options || {}))}"`;
            items.push(
                `<div class="d-flex gap-2"><span class="fw-bold text-nowrap">${escape(
                    fieldNode.string || this.props.model.fields[fieldNode.name].string
                )}</span><field name="${fieldNode.name}" ${widget} ${options}/></div>`
            );
        }
        return parseXML(`<t t-name="${CARD_ATTRIBUTE}" class="gap-2">${items.join("")}</t>`);
    }

    onEdit() {
        this.props.openRecord(this.props.record);
        this.props.close();
    }

    onDelete() {
        this.props.deleteRecord(this.props.record);
        this.props.close();
    }
}
