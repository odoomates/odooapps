/** @odoo-module **/

import { deserializeDate, deserializeDateTime, formatDate, formatDateTime } from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { formatFloat, formatInteger, formatMonetary } from "@web/views/fields/formatters";

import { _t } from "@web/core/l10n/translation";

export const NUMERIC = ["monetary", "float", "int", "percent", "ratio", "days"];
export const DETAIL_KINDS = ["detail", "opening", "closing"];

/** A value of the report, formatted for its column type. */
export function formatValue(value, type, { digits = 2, currencyId = false } = {}) {
    if (value === undefined || value === null || value === false || value === "") {
        return "";
    }
    switch (type) {
        case "monetary":
            return formatMonetary(value, { currencyId });
        case "float":
            return formatFloat(value, { digits: [16, digits] });
        case "int":
            return formatInteger(value);
        case "percent":
            return `${formatFloat(value, { digits: [16, 1] })} %`;
        case "ratio":
            return formatFloat(value, { digits: [16, 2] });
        case "days":
            return _t("%s days", formatFloat(value, { digits: [16, 1] }));
        case "datetime":
            return formatDateTime(deserializeDateTime(value), {
                format: localization.dateTimeFormat.replace(/:ss/, ""),
            });
        case "date":
            return formatDate(deserializeDate(value));
        default:
            return String(value);
    }
}

/** [{label, span}] of the header row above the columns, empty when no column has a group. */
export function headerGroups(columns) {
    if (!columns.some((column) => column.group)) {
        return [];
    }
    const groups = [];
    for (const column of columns) {
        const label = column.group || "";
        const last = groups.at(-1);
        if (last && label && last.label === label) {
            last.span += 1;
        } else {
            groups.push({ label, span: 1, key: `${groups.length}-${label}` });
        }
    }
    return groups;
}

