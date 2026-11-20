import { Component, onWillStart, onWillUpdateProps, proxy, t, useProps } from "@odoo/owl";
import { DateTimeInput } from "@web/core/datetime/datetime_input";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { _t } from "@web/core/l10n/translation";
import { deserializeDate, formatDate, serializeDate } from "@web/core/l10n/dates";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";
import { useService } from "@web/core/utils/hooks";

const { DateTime } = luxon;

/** The reports of the app, by section, with a search box. */
export class ReportSwitcher extends Component {
    static template = "om_report_engine.ReportSwitcher";
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
        return this.props.catalog.find((r) => r.model === this.props.current);
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
    static template = "om_report_engine.SavedViewsMenu";
    static components = { Dropdown, DropdownItem };
    props = useProps({
        views: t.array(),
        viewId: t.or([t.number(), t.boolean()]).optional(),
        onApply: t.function(),
        onSave: t.function(),
        onDelete: t.function(),
        onSchedule: t.function().optional(),
    });

    setup() {
        this.state = proxy({ name: "", shared: false, isDefault: false });
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
        Object.assign(this.state, { name: "", shared: false, isDefault: false });
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            this.save();
        }
    }
}

/** PDF, Excel, CSV: as on screen, or with everything unfolded. */
export class ExportMenu extends Component {
    static template = "om_report_engine.ExportMenu";
    static components = { Dropdown, DropdownItem };
    props = useProps({
        onExport: t.function(),
        exporting: t.or([t.string(), t.boolean()]).optional(),
    });
}

/** The period: the presets of the report, or a custom range; one date for "as of" reports. */
export class DateFilter extends Component {
    static template = "om_report_engine.DateFilter";
    static components = { DateTimeInput, Dropdown, DropdownItem };
    props = useProps({
        mode: t.string(),
        presets: t.array(),
        options: t.object(),
        onChange: t.function(),
    });

    get label() {
        const options = this.props.options;
        const preset = this.props.presets.find((p) => p.key === options.date_preset);
        const to = options.date_to && formatDate(deserializeDate(options.date_to));
        if (this.props.mode === "as_of") {
            return preset ? `${preset.label} (${to})` : _t("As of %s", to);
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

    /** Move the period by its own length: a month to the month before, a year to the year before... */
    shift(step) {
        const to = this.dateTo;
        if (this.props.mode === "as_of") {
            const endOfMonth = to.plus({ days: 1 }).day === 1;
            const newTo = endOfMonth ? to.plus({ months: step }).endOf("month") : to.plus({ months: step });
            this.props.onChange({ date_preset: "custom", date_to: serializeDate(newTo) });
            return;
        }
        const from = this.dateFrom;
        const months = [1, 3, 6, 12].find(
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

/** Compare with earlier periods: the one before, or the same period a year earlier; how many. */
export class CompareMenu extends Component {
    static template = "om_report_engine.CompareMenu";
    static components = { DateTimeInput, Dropdown, DropdownItem };
    props = useProps({
        choices: t.array(),
        value: t.or([t.string(), t.boolean()]).optional(),
        periods: t.number().optional(),
        label: t.string().optional(),
        // the period of the user's choice: its start (none for a report at a date) and its end
        dateFrom: t.or([t.string(), t.boolean()]).optional(),
        dateTo: t.or([t.string(), t.boolean()]).optional(),
        dateMode: t.string().optional(),
        onChange: t.function(),
    });

    get compareFrom() {
        return this.props.dateFrom ? deserializeDate(this.props.dateFrom) : false;
    }

    get compareTo() {
        return this.props.dateTo ? deserializeDate(this.props.dateTo) : false;
    }

    setCompareDate(key, value) {
        this.props.onChange({ [key]: value ? serializeDate(value) : false });
    }

    get current() {
        return this.props.choices.find((c) => c.key === this.props.value);
    }

    setPeriods(ev) {
        const value = parseInt(ev.target.value, 10);
        if (value >= 1 && value <= 12) {
            this.props.onChange({ compare_periods: value });
        }
    }
}

/** Records to filter on (journals, accounts, partners...), as tags in a dropdown. */
export class RecordFilter extends Component {
    static template = "om_report_engine.RecordFilter";
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

    async loadNames(props = this.props) {
        if (props.resIds.length) {
            this.state.names = await this.nameService.loadDisplayNames(props.filter.model, props.resIds);
        }
    }

    get label() {
        const ids = this.props.resIds;
        if (ids.length === 1 && typeof this.state.names[ids[0]] === "string") {
            return this.state.names[ids[0]];
        }
        return this.props.filter.label;
    }

    update(resIds) {
        this.props.onChange(resIds);
    }
}

/** A one-of option drawn as a dropdown of its own in the filter bar. */
export class ChoiceMenu extends Component {
    static template = "om_report_engine.ChoiceMenu";
    static components = { Dropdown, DropdownItem };
    props = useProps({
        choice: t.object(),
        value: t.any().optional(),
        onChange: t.function(),
    });

    get currentLabel() {
        const current = this.props.choice.choices.find(([value]) => value === this.props.value);
        return current ? current[1] : this.props.choice.label;
    }
}

/** On/off, one-of and numeric options of the report, and the row density. */
export class OptionsMenu extends Component {
    static template = "om_report_engine.OptionsMenu";
    static components = { Dropdown, DropdownItem };
    props = useProps({
        toggles: t.array(),
        choices: t.array(),
        numbers: t.array(),
        options: t.object(),
        density: t.string(),
        onChange: t.function(),
        onDensity: t.function(),
    });

    get activeCount() {
        return this.props.toggles.filter((toggle) => this.props.options[toggle.key]).length;
    }

    toggle(key) {
        this.props.onChange({ [key]: !this.props.options[key] });
    }

    setNumber(option, ev) {
        const value = Number(ev.target.value);
        if (!Number.isNaN(value) && value >= (option.min ?? -Infinity) && value <= (option.max ?? Infinity)) {
            this.props.onChange({ [option.key]: value });
        }
    }
}

/** The levels of grouping, in order: add, move, remove. */
export class GroupByMenu extends Component {
    static template = "om_report_engine.GroupByMenu";
    static components = { Dropdown, DropdownItem };
    props = useProps({
        available: t.array(),
        groupBy: t.array(),
        onChange: t.function(),
    });

    get chosen() {
        return this.props.groupBy.map((key) => this.props.available.find((d) => d.key === key)).filter(Boolean);
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
    static template = "om_report_engine.ColumnsMenu";
    static components = { Dropdown, DropdownItem };
    props = useProps({
        columns: t.array(),
        onChange: t.function(),
    });

    columnLabel(column) {
        return column.group ? `${column.group} · ${column.label}` : column.label;
    }

    emit(columns) {
        const optional = columns.filter((c) => c.optional);
        this.props.onChange({
            shown: optional.filter((c) => c.visible).map((c) => c.key),
            hidden: optional.filter((c) => !c.visible).map((c) => c.key),
            order: columns.map((c) => c.key),
        });
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
