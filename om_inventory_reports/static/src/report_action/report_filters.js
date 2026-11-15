import { Component, onWillStart, onWillUpdateProps, proxy, t, useProps } from "@odoo/owl";
import { DateTimeInput } from "@web/core/datetime/datetime_input";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { _t } from "@web/core/l10n/translation";
import { deserializeDate, formatDate, serializeDate } from "@web/core/l10n/dates";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";
import { useService } from "@web/core/utils/hooks";

const { DateTime } = luxon;

/** The reports, by section, with a search box. */
export class ReportSwitcher extends Component {
    static template = "om_inventory_reports.ReportSwitcher";
    static components = { Dropdown, DropdownItem };
    props = useProps({
        catalog: t.array(),
        current: t.string().optional(),
        onSelect: t.function(),
    });

    setup() {
        this.state = proxy({ search: "" });
    }

    get currentReport() {
        return this.props.catalog.find((r) => r.key === this.props.current);
    }

    get sections() {
        const needle = this.state.search.trim().toLowerCase();
        const sections = [];
        for (const report of this.props.catalog) {
            if (needle && !`${report.name} ${report.description}`.toLowerCase().includes(needle)) {
                continue;
            }
            let section = sections.find((s) => s.key === report.section);
            if (!section) {
                section = { key: report.section, name: report.section_name, reports: [] };
                sections.push(section);
            }
            section.reports.push(report);
        }
        return sections;
    }
}

/** The saved views of the report: apply, save the current one, delete. */
export class SavedViewsMenu extends Component {
    static template = "om_inventory_reports.SavedViewsMenu";
    static components = { Dropdown, DropdownItem };
    props = useProps({
        views: t.array(),
        viewId: t.or([t.number(), t.boolean()]).optional(),
        onApply: t.function(),
        onSave: t.function(),
        onDelete: t.function(),
        onSchedule: t.function(),
    });

    setup() {
        this.state = proxy({ name: "", shared: false, isDefault: false, saving: false });
    }

    get currentView() {
        return this.props.views.find((v) => v.id === this.props.viewId);
    }

    async save(overwrite = false) {
        const name = overwrite ? this.currentView.name : this.state.name.trim();
        if (!name) {
            return;
        }
        await this.props.onSave({
            name,
            shared: overwrite ? this.currentView.shared : this.state.shared,
            isDefault: overwrite ? this.currentView.is_default : this.state.isDefault,
            overwrite,
        });
        Object.assign(this.state, { name: "", shared: false, isDefault: false, saving: false });
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            this.save();
        }
    }
}

/** PDF, Excel, CSV: as on screen, or with everything unfolded. */
export class ExportMenu extends Component {
    static template = "om_inventory_reports.ExportMenu";
    static components = { Dropdown, DropdownItem };
    props = useProps({
        onExport: t.function(),
        exporting: t.or([t.string(), t.boolean()]).optional(),
    });
}

/** The period: presets, or a custom range; one date for "as of" reports. */
export class DateFilter extends Component {
    static template = "om_inventory_reports.DateFilter";
    static components = { DateTimeInput, Dropdown, DropdownItem };
    props = useProps({
        mode: t.string(),
        options: t.object(),
        onChange: t.function(),
    });

    get presets() {
        if (this.props.mode === "as_of") {
            return [
                { key: "today", label: _t("Today") },
                { key: "yesterday", label: _t("Yesterday") },
                { key: "last_week", label: _t("End of last week") },
                { key: "last_month", label: _t("End of last month") },
                { key: "last_quarter", label: _t("End of last quarter") },
                { key: "last_year", label: _t("End of last year") },
            ];
        }
        return [
            { key: "today", label: _t("Today") },
            { key: "this_week", label: _t("This week") },
            { key: "this_month", label: _t("This month") },
            { key: "this_quarter", label: _t("This quarter") },
            { key: "this_year", label: _t("This year") },
            { key: "last_week", label: _t("Last week"), separator: true },
            { key: "last_month", label: _t("Last month") },
            { key: "last_quarter", label: _t("Last quarter") },
            { key: "last_year", label: _t("Last year") },
        ];
    }

    get label() {
        const options = this.props.options;
        const preset = this.presets.find((p) => p.key === options.date_preset);
        const to = options.date_to && formatDate(deserializeDate(options.date_to));
        if (this.props.mode === "as_of") {
            return preset && options.date_preset !== "today"
                ? `${preset.label} (${to})`
                : preset
                  ? `${_t("Today")} (${to})`
                  : _t("As of %s", to);
        }
        const from = options.date_from && formatDate(deserializeDate(options.date_from));
        return preset ? `${preset.label}: ${from} - ${to}` : `${from} - ${to}`;
    }

    get dateFrom() {
        return this.props.options.date_from ? deserializeDate(this.props.options.date_from) : DateTime.local();
    }

    get dateTo() {
        return this.props.options.date_to ? deserializeDate(this.props.options.date_to) : DateTime.local();
    }

    selectPreset(key) {
        this.props.onChange({ date_preset: key });
    }

    setDate(which, value) {
        if (!value) {
            return;
        }
        const patch = {
            date_preset: "custom",
            date_from: this.props.options.date_from,
            date_to: this.props.options.date_to,
        };
        patch[which] = serializeDate(value);
        this.props.onChange(patch);
    }

    /** Move the period by its own length: a month to the month before... */
    shift(step) {
        const from = this.dateFrom;
        const to = this.dateTo;
        // whole months (a month, a quarter, a year) move by months
        const months = [1, 3, 12].find(
            (n) => from.day === 1 && from.plus({ months: n }).minus({ days: 1 }).hasSame(to, "day")
        );
        let newFrom;
        let newTo;
        if (months) {
            newFrom = from.plus({ months: months * step });
            newTo = newFrom.plus({ months }).minus({ days: 1 });
        } else {
            const days = Math.round(to.diff(from, "days").days) + 1;
            newFrom = from.plus({ days: days * step });
            newTo = to.plus({ days: days * step });
        }
        this.props.onChange({
            date_preset: "custom",
            date_from: serializeDate(newFrom),
            date_to: serializeDate(newTo),
        });
    }
}

/** Compare with the period before, or with the same period a year earlier. */
export class CompareMenu extends Component {
    static template = "om_inventory_reports.CompareMenu";
    static components = { Dropdown, DropdownItem };
    props = useProps({
        value: t.or([t.string(), t.boolean()]).optional(),
        label: t.string().optional(),
        onChange: t.function(),
    });

    get choices() {
        return [
            { key: false, label: _t("No comparison") },
            { key: "previous_period", label: _t("Previous period") },
            { key: "previous_year", label: _t("Same period last year") },
        ];
    }

    get current() {
        return this.choices.find((c) => c.key === (this.props.value || false));
    }
}

/** Records to filter on (warehouses, products...), as tags in a dropdown. */
export class RecordFilter extends Component {
    static template = "om_inventory_reports.RecordFilter";
    static components = { Dropdown, MultiRecordSelector };
    props = useProps({
        filter: t.object(),
        resIds: t.array(),
        onChange: t.function(),
    });

    setup() {
        this.nameService = useService("name");
        this.state = proxy({ names: {} });
        onWillStart(() => this.loadNames());
        onWillUpdateProps((next) => this.loadNames(next));
    }

    get placeholder() {
        return _t("Search...");
    }

    async onOpened() {
        await this.loadNames();
    }

    async loadNames(props = this.props) {
        if (props.resIds.length) {
            this.state.names = await this.nameService.loadDisplayNames(props.filter.model, props.resIds);
        }
    }

    get label() {
        const ids = this.props.resIds;
        if (!ids.length) {
            return this.props.filter.label;
        }
        if (ids.length === 1 && typeof this.state.names[ids[0]] === "string") {
            return this.state.names[ids[0]];
        }
        return this.props.filter.label;
    }

    update(resIds) {
        this.props.onChange(resIds);
    }
}

/** On/off options and numeric options of the report, and the row density. */
export class OptionsMenu extends Component {
    static template = "om_inventory_reports.OptionsMenu";
    static components = { Dropdown, DropdownItem };
    props = useProps({
        toggles: t.array(),
        extraOptions: t.array(),
        options: t.object(),
        density: t.string(),
        onChange: t.function(),
        onDensity: t.function(),
    });

    toggle(key) {
        this.props.onChange({ [key]: !this.props.options[key] });
    }

    setNumber(option, ev) {
        const value = Number(ev.target.value);
        if (!Number.isNaN(value) && value >= (option.min ?? -Infinity)) {
            this.props.onChange({ [option.key]: value });
        }
    }
}

/** The levels of grouping, in order: add, move, remove. */
export class GroupByMenu extends Component {
    static template = "om_inventory_reports.GroupByMenu";
    static components = { Dropdown, DropdownItem };
    props = useProps({
        available: t.array(),
        groupBy: t.array(),
        onChange: t.function(),
    });

    get chosen() {
        return this.props.groupBy
            .map((key) => this.props.available.find((d) => d.key === key))
            .filter(Boolean);
    }

    get others() {
        return this.props.available.filter((d) => !this.props.groupBy.includes(d.key));
    }

    get label() {
        return this.chosen.map((d) => d.label).join(" › ");
    }

    add(key) {
        if (this.props.groupBy.length < 3) {
            this.props.onChange([...this.props.groupBy, key]);
        }
    }

    remove(key) {
        if (this.props.groupBy.length > 1) {
            this.props.onChange(this.props.groupBy.filter((k) => k !== key));
        }
    }

    move(index, step) {
        const groupBy = [...this.props.groupBy];
        const [item] = groupBy.splice(index, 1);
        groupBy.splice(index + step, 0, item);
        this.props.onChange(groupBy);
    }
}

/** The columns: show, hide, reorder. */
export class ColumnsMenu extends Component {
    static template = "om_inventory_reports.ColumnsMenu";
    static components = { Dropdown, DropdownItem };
    props = useProps({
        columns: t.array(),
        onChange: t.function(),
    });

    get optionalColumns() {
        return this.props.columns.filter((c) => c.optional);
    }

    emit(columns) {
        this.props.onChange(columns.filter((c) => c.visible || !c.optional).map((c) => c.key));
    }

    toggle(column) {
        this.emit(this.props.columns.map((c) => (c.key === column.key ? { ...c, visible: !c.visible } : c)));
    }

    move(column, step) {
        const columns = [...this.props.columns];
        const index = columns.findIndex((c) => c.key === column.key);
        const target = index + step;
        if (target < 0 || target >= columns.length) {
            return;
        }
        [columns[index], columns[target]] = [columns[target], columns[index]];
        this.emit(columns);
    }

    reset() {
        this.props.onChange(false);
    }
}
