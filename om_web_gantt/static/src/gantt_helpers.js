import { _t } from "@web/core/l10n/translation";
import {
    deserializeDate,
    deserializeDateTime,
    getStartOfLocalWeek,
    serializeDate,
    serializeDateTime,
} from "@web/core/l10n/dates";

const { DateTime } = luxon;

export const GANTT_SCALES = ["day", "week", "month", "year"];

export const SCALE_LABELS = {
    day: _t("Day"),
    week: _t("Week"),
    month: _t("Month"),
    year: _t("Year"),
};

/**
 * Number of snapping steps in one column of each scale, per precision.
 * A column is an hour in the day scale, a day in the week and month scales
 * and a month in the year scale.
 */
const PRECISION_STEPS = {
    day: { "hour:full": 1, "hour:half": 2, "hour:quarter": 4 },
    week: { "day:full": 1, "day:half": 2 },
    month: { "day:full": 1, "day:half": 2 },
    year: { "month:full": 1, "month:half": 2 },
};

export const DEFAULT_PRECISION = {
    day: "hour:half",
    week: "day:half",
    month: "day:half",
    year: "month:full",
};

/**
 * @param {string} scale
 * @param {string} precision
 * @param {boolean} dateOnly whether the start and stop fields are date fields
 * @returns {number} steps per column (can be lower than 1)
 */
export function getStepsPerColumn(scale, precision, dateOnly) {
    let steps = PRECISION_STEPS[scale][precision] || PRECISION_STEPS[scale][DEFAULT_PRECISION[scale]];
    if (dateOnly) {
        if (scale === "day") {
            steps = 1 / 24;
        } else if (scale !== "year") {
            steps = 1;
        }
    }
    return steps;
}

/**
 * @param {DateTime} focusDate
 * @param {string} scale
 * @returns {{ start: DateTime, stop: DateTime }}
 */
export function getRange(focusDate, scale) {
    let start;
    let stop;
    switch (scale) {
        case "day":
            start = focusDate.startOf("day");
            stop = start.plus({ days: 1 });
            break;
        case "week":
            start = getStartOfLocalWeek(focusDate);
            stop = start.plus({ days: 7 });
            break;
        case "month":
            start = focusDate.startOf("month");
            stop = start.plus({ months: 1 });
            break;
        default:
            start = focusDate.startOf("year");
            stop = start.plus({ years: 1 });
    }
    return { start, stop };
}

/**
 * @param {{ start: DateTime, stop: DateTime }} range
 * @param {string} scale
 */
export function getColumns(range, scale) {
    const unit = { day: "hours", week: "days", month: "days", year: "months" }[scale];
    const now = DateTime.local();
    const columns = [];
    let start = range.start;
    let index = 0;
    while (start < range.stop) {
        const stop = start.plus({ [unit]: 1 });
        const column = { index, start, stop, isToday: false, isWeekend: false };
        if (scale === "day") {
            column.label = start.toFormat("HH");
            column.isToday = now >= start && now < stop;
        } else if (scale === "year") {
            column.label = start.toFormat("MMM");
            column.isToday = start.hasSame(now, "month");
        } else {
            column.label = scale === "week" ? start.toFormat("ccc d") : start.toFormat("d");
            column.subLabel = scale === "month" ? start.toFormat("ccccc") : "";
            column.isToday = start.hasSame(now, "day");
            column.isWeekend = start.weekday > 5;
        }
        columns.push(column);
        start = stop;
        index++;
    }
    return columns;
}

/**
 * Position of a date on the columns, as a float number of columns from the
 * start of the range. Columns all have the same width, even if months do not
 * have the same number of days, hence the computation per column.
 *
 * @param {DateTime} date
 * @param {Object[]} columns
 */
export function dateToPosition(date, columns) {
    const ts = date.toMillis();
    if (ts <= columns[0].start.toMillis()) {
        return 0;
    }
    const last = columns[columns.length - 1];
    if (ts >= last.stop.toMillis()) {
        return columns.length;
    }
    for (const column of columns) {
        const start = column.start.toMillis();
        const stop = column.stop.toMillis();
        if (ts >= start && ts < stop) {
            return column.index + (ts - start) / (stop - start);
        }
    }
    return columns.length;
}

/**
 * Inverse of dateToPosition. Positions outside the range are extrapolated with
 * the size of the first or last column.
 *
 * @param {number} position
 * @param {Object[]} columns
 * @returns {DateTime}
 */
export function positionToDate(position, columns) {
    const count = columns.length;
    let index = Math.floor(position);
    let fraction = position - index;
    let base;
    if (index < 0) {
        base = columns[0];
        const size = base.stop.toMillis() - base.start.toMillis();
        return DateTime.fromMillis(base.start.toMillis() + position * size);
    }
    if (index >= count) {
        base = columns[count - 1];
        fraction += index - (count - 1);
        index = count - 1;
    } else {
        base = columns[index];
    }
    const size = base.stop.toMillis() - base.start.toMillis();
    return DateTime.fromMillis(base.start.toMillis() + fraction * size);
}

export function snapPosition(position, stepsPerColumn) {
    return Math.round(position * stepsPerColumn) / stepsPerColumn;
}

export function parseFieldDate(value, fieldType, isStop) {
    if (!value) {
        return null;
    }
    if (fieldType === "date") {
        const date = deserializeDate(value).startOf("day");
        return isStop ? date.plus({ days: 1 }) : date;
    }
    return deserializeDateTime(value);
}

export function serializeFieldDate(date, fieldType, isStop) {
    if (fieldType === "date") {
        let day = date.plus({ hours: 12 }).startOf("day");
        if (isStop) {
            day = day.minus({ days: 1 });
        }
        return serializeDate(day);
    }
    return serializeDateTime(date);
}

/**
 * Title of the visible range, shown next to the navigation buttons.
 */
export function getRangeTitle(range, scale) {
    const { start } = range;
    switch (scale) {
        case "day":
            return start.toFormat("cccc d MMMM yyyy");
        case "week": {
            const end = range.stop.minus({ days: 1 });
            if (start.month === end.month) {
                return `${start.toFormat("d")} - ${end.toFormat("d MMMM yyyy")}`;
            }
            if (start.year === end.year) {
                return `${start.toFormat("d MMM")} - ${end.toFormat("d MMM yyyy")}`;
            }
            return `${start.toFormat("d MMM yyyy")} - ${end.toFormat("d MMM yyyy")}`;
        }
        case "month":
            return start.toFormat("MMMM yyyy");
        default:
            return start.toFormat("yyyy");
    }
}

/**
 * Assigns a lane to each pill so that pills of a row do not overlap.
 *
 * @param {{ left: number, right: number }[]} pills sorted by left
 * @returns {number} number of lanes
 */
export function assignLanes(pills) {
    const laneEnds = [];
    for (const pill of pills) {
        let lane = laneEnds.findIndex((end) => end <= pill.left + 1e-6);
        if (lane === -1) {
            lane = laneEnds.length;
            laneEnds.push(pill.right);
        } else {
            laneEnds[lane] = pill.right;
        }
        pill.lane = lane;
    }
    return laneEnds.length;
}

/**
 * Escapes a text to put it in an XML arch built as a string.
 *
 * @param {string} text
 */
export function escapeXml(text) {
    return String(text ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}
