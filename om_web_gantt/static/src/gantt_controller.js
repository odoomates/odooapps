import { Component, signal, t, useProps } from "@odoo/owl";

import {
    ConfirmationDialog,
    deleteConfirmationMessage,
} from "@web/core/confirmation_dialog/confirmation_dialog";
import { DateTimePicker } from "@web/core/datetime/datetime_picker";
import { _t } from "@web/core/l10n/translation";
import { usePopover } from "@web/core/popover/popover_hook";
import { useOwnedDialogs, useService } from "@web/core/utils/hooks";
import { useModel } from "@web/model/model";
import { useSetupAction } from "@web/search/action_hook";
import { CogMenu } from "@web/search/cog_menu/cog_menu";
import { Layout } from "@web/search/layout";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { useSearchBarToggler } from "@web/search/search_bar/search_bar_toggler";
import { standardViewProps } from "@web/views/standard_view_props";
import { ViewScaleSelector } from "@web/views/view_components/view_scale_selector";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { SelectCreateDialog } from "@web/views/view_dialogs/select_create_dialog";
import { getRangeTitle, SCALE_LABELS } from "./gantt_helpers";

const { DateTime } = luxon;

class GanttDatePicker extends Component {
    static template = "om_web_gantt.GanttDatePicker";
    static components = { DateTimePicker };
    props = useProps(["close", "value", "onSelect"]);

    get pickerProps() {
        return {
            type: "date",
            value: this.props.value,
            onSelect: (date) => {
                this.props.onSelect(date);
                this.props.close();
            },
        };
    }
}

export class GanttController extends Component {
    static template = "om_web_gantt.GanttController";
    static components = { Layout, CogMenu, SearchBar, ViewScaleSelector };

    props = useProps({
        ...standardViewProps,
        Model: t.function(),
        Renderer: t.function(),
        archInfo: t.object(),
        buttonTemplate: t.string(),
    });

    rootRef = signal.ref();

    setup() {
        this.actionService = useService("action");
        this.addDialog = useOwnedDialogs();
        this.model = useModel(this.props.Model, {
            archInfo: this.props.archInfo,
            resModel: this.props.resModel,
            fields: this.props.fields,
            state: this.props.state?.ganttState,
        });
        useSetupAction({
            rootRef: this.rootRef,
            getLocalState: () => ({ ganttState: this.model.exportState() }),
        });
        this.searchBarToggler = useSearchBarToggler();
        this.datePickerPopover = usePopover(GanttDatePicker, { position: "bottom-start" });
    }

    get rangeTitle() {
        return this.model.data.range ? getRangeTitle(this.model.data.range, this.model.scale) : "";
    }

    get scales() {
        return Object.fromEntries(
            this.props.archInfo.scales.map((scale) => [scale, { description: SCALE_LABELS[scale] }])
        );
    }

    get rendererProps() {
        return {
            model: this.model,
            archInfo: this.props.archInfo,
            openRecord: this.openRecord.bind(this),
            deleteRecord: this.deleteRecord.bind(this),
            createRecord: this.createRecord.bind(this),
            planRecords: this.planRecords.bind(this),
        };
    }

    setScale(scale) {
        this.model.load({ scale });
    }

    navigate(direction) {
        const { focusDate, scale } = this.model.meta;
        let date;
        if (direction === "today") {
            date = DateTime.local();
        } else {
            const delta = { [`${scale}s`]: direction === "next" ? 1 : -1 };
            date = focusDate.plus(delta);
        }
        this.model.load({ focusDate: date });
    }

    openDatePicker(ev) {
        if (this.datePickerPopover.isOpen) {
            this.datePickerPopover.close();
            return;
        }
        this.datePickerPopover.open(ev.currentTarget, {
            value: this.model.meta.focusDate,
            onSelect: (date) => date && this.model.load({ focusDate: date }),
        });
    }

    onClickNew() {
        const { columns } = this.model.data;
        const now = DateTime.local();
        const column = columns.find((col) => now >= col.start && now < col.stop) || columns[0];
        if (!column) {
            return;
        }
        const period = this.model.getCellPeriod(column.index);
        this.createRecord({ ...period, row: null });
    }

    /**
     * @param {Object} params
     * @param {DateTime} params.start
     * @param {DateTime} params.stop
     * @param {Object|null} params.row
     */
    createRecord(params) {
        if (!this.model.canCreate) {
            return;
        }
        const context = this.model.getContextDefaults(params);
        this.addDialog(FormViewDialog, {
            resModel: this.props.resModel,
            context,
            title: _t("New"),
            viewId: this.props.archInfo.formViewId,
            onRecordSaved: () => this.model.load(),
        });
    }

    planRecords(params) {
        if (!this.model.canWrite) {
            return;
        }
        this.addDialog(SelectCreateDialog, {
            resModel: this.props.resModel,
            title: _t("Plan existing"),
            domain: this.model.getPlanDomain(),
            context: this.model.meta.context,
            noCreate: !this.model.canCreate,
            onSelected: async (resIds) => {
                if (resIds.length) {
                    await this.model.planRecords(resIds, params);
                }
            },
            onCreateEdit: () => this.createRecord(params),
        });
    }

    openRecord(record) {
        this.addDialog(FormViewDialog, {
            resModel: this.props.resModel,
            resId: record.id,
            context: this.model.meta.context,
            title: _t("Open: %s", record.displayName),
            viewId: this.props.archInfo.formViewId,
            preventEdit: !this.model.canWrite,
            onRecordSaved: () => this.model.load(),
        });
    }

    deleteRecord(record) {
        this.addDialog(ConfirmationDialog, {
            title: _t("Bye-bye, record!"),
            body: deleteConfirmationMessage,
            confirm: () => this.model.unlinkRecord(record.id),
            confirmLabel: _t("Delete"),
            confirmClass: "btn-danger",
            cancel: () => {},
            cancelLabel: _t("No, keep it"),
        });
    }
}
