import { _t } from "@web/core/l10n/translation";
import { Domain } from "@web/core/domain";
import { evaluateBooleanExpr } from "@web/core/py_js/py";
import { serializeDateTime } from "@web/core/l10n/dates";
import { user } from "@web/core/user";
import { KeepLast } from "@web/core/utils/concurrency";
import { Model } from "@web/model/model";
import {
    assignLanes,
    dateToPosition,
    getColumns,
    getRange,
    getStepsPerColumn,
    parseFieldDate,
    positionToDate,
    serializeFieldDate,
    snapPosition,
} from "./gantt_helpers";

const { DateTime } = luxon;

/** Field types a pill can be dropped on (the value of the row is written). */
const WRITABLE_GROUP_TYPES = [
    "many2one",
    "many2many",
    "selection",
    "char",
    "integer",
    "boolean",
];

export class GanttModel extends Model {
    setup(params) {
        this.archInfo = params.archInfo;
        this.resModel = params.resModel;
        this.fields = params.fields;
        this.keepLast = new KeepLast();
        const state = params.state || {};
        this.meta = {
            scale: state.scale || this.archInfo.defaultScale,
            focusDate: state.focusDate ? DateTime.fromISO(state.focusDate) : DateTime.local(),
            domain: [],
            context: {},
            groupBy: [],
            orderBy: [],
        };
        this.canWrite = this.archInfo.activeActions.edit;
        this.canCreate = this.archInfo.activeActions.create;
        this.canDelete = this.archInfo.activeActions.delete;
        this.data = this.emptyData();
    }

    emptyData() {
        return {
            records: {},
            rows: [],
            columns: [],
            range: null,
            length: 0,
            unavailabilities: {},
            progressBars: {},
        };
    }

    // -------------------------------------------------------------------------
    // Getters
    // -------------------------------------------------------------------------

    get scale() {
        return this.meta.scale;
    }

    get dateOnly() {
        const { dateStartField, dateStopField } = this.archInfo;
        return (
            this.fields[dateStartField].type === "date" &&
            this.fields[dateStopField].type === "date"
        );
    }

    get stepsPerColumn() {
        return getStepsPerColumn(
            this.meta.scale,
            this.archInfo.precision[this.meta.scale],
            this.dateOnly
        );
    }

    get groupBy() {
        return this.meta.groupBy;
    }

    /** @returns {boolean} the start and stop fields can be changed */
    get datesWritable() {
        const { dateStartField, dateStopField } = this.archInfo;
        return !this.fields[dateStartField].readonly && !this.fields[dateStopField].readonly;
    }

    get canDrag() {
        return this.canWrite && this.datesWritable;
    }

    hasData() {
        return Object.keys(this.data.records).length > 0;
    }

    exportState() {
        return {
            scale: this.meta.scale,
            focusDate: this.meta.focusDate.toISO(),
        };
    }

    // -------------------------------------------------------------------------
    // Load
    // -------------------------------------------------------------------------

    /**
     * @param {Object} [params] search params (domain, context, groupBy,
     *  orderBy) and/or scale and focusDate
     */
    async load(params = {}) {
        const meta = { ...this.meta };
        if ("domain" in params) {
            meta.domain = params.domain;
        }
        if ("context" in params) {
            meta.context = params.context;
        }
        if ("groupBy" in params) {
            meta.groupBy = params.groupBy.length ? params.groupBy : this.archInfo.defaultGroupBy;
        }
        if ("orderBy" in params) {
            meta.orderBy = params.orderBy?.length ? params.orderBy : this.archInfo.defaultOrder;
        }
        if (params.scale) {
            meta.scale = params.scale;
        }
        if (params.focusDate) {
            meta.focusDate = params.focusDate;
        }
        if (!this.accessChecked) {
            const [write, create, unlink] = await Promise.all([
                user.checkAccessRight(this.resModel, "write"),
                user.checkAccessRight(this.resModel, "create"),
                user.checkAccessRight(this.resModel, "unlink"),
            ]);
            this.canWrite = this.archInfo.activeActions.edit && write;
            this.canCreate = this.archInfo.activeActions.create && create;
            this.canDelete = this.archInfo.activeActions.delete && unlink;
            this.accessChecked = true;
        }
        const data = await this.keepLast.add(this.fetchData(meta));
        this.meta = meta;
        this.data = data;
        this.notify();
    }

    getReadSpecification() {
        const spec = {};
        for (const fieldName of this.archInfo.fieldNames) {
            const field = this.fields[fieldName];
            if (!field) {
                continue;
            }
            if (field.type === "many2one") {
                spec[fieldName] = { fields: { display_name: {} } };
            } else {
                spec[fieldName] = {};
            }
        }
        // values of the rows, to know which value a pill is moved from
        for (const groupBy of this.meta.groupBy) {
            const fieldName = groupBy.split(":")[0];
            const field = this.fields[fieldName];
            if (field && !(fieldName in spec)) {
                spec[fieldName] = field.type === "many2one" ? { fields: { display_name: {} } } : {};
            }
        }
        return spec;
    }

    async fetchData(meta) {
        const { dateStartField, dateStopField } = this.archInfo;
        const range = getRange(meta.focusDate, meta.scale);
        const columns = getColumns(range, meta.scale);
        const startType = this.fields[dateStartField].type;
        const stopType = this.fields[dateStopField].type;
        const startFrom =
            startType === "date" ? range.start.toISODate() : serializeDateTime(range.start);
        const rangeStop =
            startType === "date" ? range.stop.toISODate() : serializeDateTime(range.stop);
        const rangeStart =
            stopType === "date" ? range.start.toISODate() : serializeDateTime(range.start);
        const stopCompare = stopType === "date" ? ">=" : ">";
        const domain = Domain.and([
            meta.domain,
            [
                [dateStartField, "<", rangeStop],
                "|",
                [dateStopField, stopCompare, rangeStart],
                "&",
                [dateStopField, "=", false],
                [dateStartField, ">=", startFrom],
            ],
        ]).toList();
        const groupBy = meta.groupBy.filter((gb) => gb.split(":")[0] in this.fields);
        const order = meta.orderBy
            .map((o) => `${o.name} ${o.asc ? "ASC" : "DESC"}`)
            .join(", ");
        const kwargs = {
            order: order || `${dateStartField} ASC`,
            context: meta.context,
            gantt_range: {
                start: serializeDateTime(range.start),
                stop: serializeDateTime(range.stop),
                scale: meta.scale,
            },
            unavailability: this.archInfo.displayUnavailability,
            progress_bar_fields: this.archInfo.progressBarFields,
        };
        const result = await this.orm.call(
            this.resModel,
            "get_gantt_data",
            [domain, groupBy, this.getReadSpecification()],
            kwargs
        );
        const data = this.emptyData();
        data.range = range;
        data.columns = columns;
        data.length = result.length;
        data.groupBy = groupBy;
        for (const raw of result.records) {
            const record = this.processRecord(raw, columns, startType, stopType);
            if (record) {
                data.records[record.id] = record;
            }
        }
        for (const item of result.unavailabilities || []) {
            const key = JSON.stringify(item.path);
            data.unavailabilities[key] = item.unavailabilities.map((period) => {
                const start = parseFieldDate(period.start, "datetime");
                const stop = parseFieldDate(period.stop, "datetime");
                const left = dateToPosition(start, columns);
                const right = dateToPosition(stop, columns);
                return { left, width: Math.max(right - left, 0) };
            });
        }
        data.progressBars = result.progress_bars || {};
        data.rows = this.buildRows(groupBy, result.groups, data);
        return data;
    }

    processRecord(raw, columns, startType, stopType) {
        const { dateStartField, dateStopField, colorField, progressField, consolidationField } =
            this.archInfo;
        const start = parseFieldDate(raw[dateStartField], startType, false);
        let stop = parseFieldDate(raw[dateStopField], stopType, true);
        if (!start) {
            return null;
        }
        if (!stop || stop < start) {
            stop = start;
        }
        const left = dateToPosition(start, columns);
        const right = dateToPosition(stop, columns);
        let colorIndex = 0;
        if (colorField) {
            const value = raw[colorField];
            if (typeof value === "number") {
                colorIndex = value;
            } else if (value && typeof value === "object" && value.id) {
                colorIndex = value.id;
            } else if (Array.isArray(value) && value.length) {
                colorIndex = value[0];
            }
            colorIndex = Math.abs(colorIndex) % 12;
        }
        let progress = null;
        if (progressField && raw[progressField] !== false) {
            progress = Math.max(0, Math.min(100, Number(raw[progressField]) || 0));
        }
        return {
            id: raw.id,
            raw,
            decorations: this.getDecorations(raw),
            displayName: raw.display_name || "",
            start,
            stop,
            left,
            right,
            colorIndex,
            progress,
            consolidation: consolidationField ? Number(raw[consolidationField]) || 0 : 0,
            dependencies: this.archInfo.dependencyField
                ? raw[this.archInfo.dependencyField] || []
                : [],
            startsBefore: start < columns[0].start,
            stopsAfter: stop > columns[columns.length - 1].stop,
        };
    }

    /**
     * @param {Object} raw values of the record (web_read format)
     * @returns {string[]} the decorations (info, warning, striped...) of its pill
     */
    getDecorations(raw) {
        if (!this.archInfo.decorations.length) {
            return [];
        }
        const evalContext = { context: this.meta.context };
        for (const [name, value] of Object.entries(raw)) {
            if (value && typeof value === "object" && !Array.isArray(value)) {
                evalContext[name] = value.id || false;
            } else {
                evalContext[name] = value;
            }
        }
        return this.archInfo.decorations
            .filter(({ condition }) => {
                try {
                    return evaluateBooleanExpr(condition, evalContext);
                } catch {
                    return false;
                }
            })
            .map(({ name }) => name);
    }

    /**
     * Builds the nested rows from the groups returned by the server.
     */
    buildRows(groupBy, groups, data) {
        const allIds = Object.keys(data.records).map(Number);
        if (!groupBy.length) {
            const row = this.makeRow([], [], null, null, 0);
            row.label = this.archInfo.string || "";
            row.recordIds = allIds;
            this.finalizeRow(row, data);
            return [row];
        }
        const root = { children: [], childByKey: {} };
        for (const group of groups) {
            let parent = root;
            const path = [];
            const ids = (group["id:array_agg"] || []).filter((id) => id in data.records);
            groupBy.forEach((spec, level) => {
                const { value, label } = this.getGroupValue(spec, group[spec]);
                path.push(value);
                const key = JSON.stringify(path);
                let row = parent.childByKey[key];
                if (!row) {
                    row = this.makeRow(groupBy.slice(0, level + 1), [...path], spec, value, level);
                    row.label = label;
                    parent.children.push(row);
                    parent.childByKey[key] = row;
                }
                for (const id of ids) {
                    if (!row.recordIdSet.has(id)) {
                        row.recordIdSet.add(id);
                        row.recordIds.push(id);
                    }
                }
                parent = row;
            });
        }
        const finalize = (rows) => {
            for (const row of rows) {
                finalize(row.children);
                this.finalizeRow(row, data);
            }
        };
        finalize(root.children);
        return root.children;
    }

    makeRow(groupedBy, path, spec, value, level) {
        const fieldName = spec ? spec.split(":")[0] : null;
        return {
            key: JSON.stringify(path),
            path,
            groupedBy,
            groupBy: spec,
            fieldName,
            value,
            level,
            label: "",
            children: [],
            childByKey: {},
            recordIds: [],
            recordIdSet: new Set(),
        };
    }

    getGroupValue(spec, rawValue) {
        const fieldName = spec.split(":")[0];
        const field = this.fields[fieldName];
        if (Array.isArray(rawValue)) {
            return {
                value: rawValue[0],
                label: rawValue[1] || this.archInfo.emptyRowLabels[fieldName] || _t("None"),
            };
        }
        if (rawValue === false || rawValue === null || rawValue === undefined) {
            if (field?.type === "boolean") {
                return { value: false, label: _t("No") };
            }
            return { value: false, label: this.archInfo.emptyRowLabels[fieldName] || _t("None") };
        }
        if (field?.type === "selection") {
            const option = field.selection.find(([key]) => key === rawValue);
            return { value: rawValue, label: option ? option[1] : String(rawValue) };
        }
        if (field?.type === "boolean") {
            return { value: rawValue, label: rawValue ? _t("Yes") : _t("No") };
        }
        return { value: rawValue, label: String(rawValue) };
    }

    finalizeRow(row, data) {
        const records = row.recordIds.map((id) => data.records[id]);
        row.isGroup = row.children.length > 0;
        row.unavailabilities = data.unavailabilities[row.key] || [];
        row.total = records.reduce((sum, record) => sum + record.consolidation, 0);
        row.recordCount = records.length;
        if (row.fieldName && this.archInfo.thumbnails[row.fieldName] && row.value) {
            const field = this.fields[row.fieldName];
            if (field.relation) {
                row.thumbnail = `/web/image/${field.relation}/${row.value}/${
                    this.archInfo.thumbnails[row.fieldName]
                }`;
            }
        }
        row.progressBar = null;
        const bars = row.fieldName && row.value !== false && data.progressBars[row.fieldName];
        if (bars && bars[String(row.value)]) {
            const bar = bars[String(row.value)];
            const value = Number(bar.value) || 0;
            const barMax = Number(bar.max) || 0;
            row.progressBar = {
                value,
                max: barMax,
                label: bar.label,
                ratio: barMax ? Math.min((value / barMax) * 100, 100) : value ? 100 : 0,
                overCapacity: barMax ? value > barMax : value > 0,
            };
        }
        const max = this.getConsolidationMax(row);
        row.consolidationMax = max;
        if (row.isGroup || this.archInfo.consolidationField) {
            row.aggregates = this.computeAggregates(records, data.columns, max);
        } else {
            row.aggregates = [];
        }
        if (!row.isGroup) {
            const pills = records
                .map((record) => ({
                    record,
                    left: Math.max(record.left, 0),
                    right: Math.max(record.right, record.left + 0.0001),
                }))
                .sort((a, b) => a.left - b.left || b.right - a.right);
            row.laneCount = Math.max(assignLanes(pills), 1);
            row.pills = pills;
        } else {
            row.pills = [];
            row.laneCount = 1;
        }
        delete row.childByKey;
        delete row.recordIdSet;
    }

    getConsolidationMax(row) {
        if (!this.archInfo.consolidationField) {
            return null;
        }
        // the closest groupby of the row (or its parents) with a maximum
        for (let index = row.groupedBy.length - 1; index >= 0; index--) {
            const fieldName = row.groupedBy[index].split(":")[0];
            if (fieldName in this.archInfo.consolidationMax) {
                return index === row.groupedBy.length - 1
                    ? this.archInfo.consolidationMax[fieldName]
                    : null;
            }
        }
        return null;
    }

    /**
     * Per column: the number of records (or the sum of the consolidation field)
     * overlapping the column.
     */
    computeAggregates(records, columns, max) {
        const field = this.archInfo.consolidationField;
        const aggregates = [];
        let current = null;
        for (const column of columns) {
            let value = 0;
            let count = 0;
            for (const record of records) {
                if (record.left < column.index + 1 && record.right > column.index) {
                    value += field ? record.consolidation : 1;
                    count++;
                }
            }
            if (!count) {
                current = null;
                continue;
            }
            const overCapacity = max !== null && max !== undefined && value > max;
            // merge consecutive columns with the same value
            if (current && current.value === value && current.overCapacity === overCapacity) {
                current.width += 1;
            } else {
                current = { left: column.index, width: 1, value, count, overCapacity };
                aggregates.push(current);
            }
        }
        return aggregates;
    }

    get totalAggregates() {
        const records = Object.values(this.data.records);
        return this.computeAggregates(records, this.data.columns, null);
    }

    get totalValue() {
        const records = Object.values(this.data.records);
        if (this.archInfo.consolidationField) {
            return records.reduce((sum, record) => sum + record.consolidation, 0);
        }
        return records.length;
    }

    // -------------------------------------------------------------------------
    // Positions and values
    // -------------------------------------------------------------------------

    positionToDate(position) {
        const snapped = snapPosition(position, this.stepsPerColumn);
        return positionToDate(snapped, this.data.columns);
    }

    /**
     * @param {number} columnIndex
     * @returns {{ start: DateTime, stop: DateTime }} the period of a cell
     */
    getCellPeriod(columnIndex) {
        const column = this.data.columns[columnIndex];
        let { start, stop } = column;
        if (this.dateOnly && this.meta.scale === "day") {
            start = this.data.range.start;
            stop = this.data.range.stop;
        } else if (!this.dateOnly && this.meta.scale !== "day") {
            // a day (or a month) ends at its last second, not at the next midnight
            stop = stop.minus({ seconds: 1 });
        }
        return { start, stop };
    }

    /** @returns {Object} values of the grouped fields of a row, for a write/create */
    getRowValues(row, forContext = false) {
        const values = {};
        if (!row) {
            return values;
        }
        row.groupedBy.forEach((spec, index) => {
            if (spec.includes(":")) {
                return;
            }
            const field = this.fields[spec];
            if (!field || !WRITABLE_GROUP_TYPES.includes(field.type) || field.readonly) {
                return;
            }
            const value = row.path[index];
            if (field.type === "many2many") {
                if (value) {
                    values[spec] = forContext ? [value] : [[4, value]];
                }
            } else {
                values[spec] = value;
            }
        });
        return values;
    }

    /** @returns {boolean} whether a pill of `fromRow` can be moved to `toRow` */
    canMoveToRow(fromRow, toRow) {
        if (!fromRow || !toRow || fromRow.key === toRow.key) {
            return true;
        }
        return toRow.groupedBy.every((spec, index) => {
            if (fromRow.path[index] === toRow.path[index]) {
                return true;
            }
            const field = this.fields[spec];
            return (
                !spec.includes(":") &&
                field &&
                WRITABLE_GROUP_TYPES.includes(field.type) &&
                !field.readonly &&
                field.store !== false
            );
        });
    }

    getContextDefaults({ start, stop, row }) {
        const { dateStartField, dateStopField } = this.archInfo;
        const context = { ...this.meta.context };
        context[`default_${dateStartField}`] = serializeFieldDate(
            start,
            this.fields[dateStartField].type,
            false
        );
        context[`default_${dateStopField}`] = serializeFieldDate(
            stop,
            this.fields[dateStopField].type,
            true
        );
        for (const [fieldName, value] of Object.entries(this.getRowValues(row, true))) {
            if (value !== false) {
                context[`default_${fieldName}`] = value;
            }
        }
        return context;
    }

    // -------------------------------------------------------------------------
    // Write
    // -------------------------------------------------------------------------

    /**
     * @param {number} recordId
     * @param {Object} params
     * @param {DateTime} [params.start]
     * @param {DateTime} [params.stop]
     * @param {Object} [params.fromRow]
     * @param {Object} [params.toRow]
     */
    async reschedule(recordId, { start, stop, fromRow, toRow }) {
        const { dateStartField, dateStopField } = this.archInfo;
        const vals = {};
        if (start) {
            vals[dateStartField] = serializeFieldDate(start, this.fields[dateStartField].type, false);
        }
        if (stop) {
            vals[dateStopField] = serializeFieldDate(stop, this.fields[dateStopField].type, true);
        }
        if (fromRow && toRow && fromRow.key !== toRow.key) {
            toRow.groupedBy.forEach((spec, index) => {
                const newValue = toRow.path[index];
                const oldValue = fromRow.path[index];
                if (newValue === oldValue || spec.includes(":")) {
                    return;
                }
                const field = this.fields[spec];
                if (!field || !WRITABLE_GROUP_TYPES.includes(field.type) || field.readonly) {
                    return;
                }
                if (field.type === "many2many") {
                    const commands = [];
                    if (oldValue) {
                        commands.push([3, oldValue]);
                    }
                    if (newValue) {
                        commands.push([4, newValue]);
                    }
                    vals[spec] = commands;
                } else {
                    vals[spec] = newValue;
                }
            });
        }
        if (!Object.keys(vals).length) {
            return;
        }
        try {
            await this.orm.write(this.resModel, [recordId], vals, { context: this.meta.context });
        } finally {
            await this.load();
        }
    }

    async planRecords(resIds, { start, stop, row }) {
        const { dateStartField, dateStopField } = this.archInfo;
        const vals = {
            [dateStartField]: serializeFieldDate(start, this.fields[dateStartField].type, false),
            [dateStopField]: serializeFieldDate(stop, this.fields[dateStopField].type, true),
            ...this.getRowValues(row),
        };
        try {
            await this.orm.write(this.resModel, resIds, vals, { context: this.meta.context });
        } finally {
            await this.load();
        }
    }

    async unlinkRecord(resId) {
        await this.orm.unlink(this.resModel, [resId], { context: this.meta.context });
        await this.load();
    }

    getPlanDomain() {
        const { dateStartField, dateStopField } = this.archInfo;
        return Domain.and([
            this.meta.domain,
            ["|", [dateStartField, "=", false], [dateStopField, "=", false]],
        ]).toList();
    }
}
