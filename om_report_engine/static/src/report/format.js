import { getCurrency } from "@web/core/currency";
import { deserializeDate, deserializeDateTime, formatDate, formatDateTime } from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { formatFloat, formatInteger, formatMonetary } from "@web/views/fields/formatters";

import { _t } from "@web/core/l10n/translation";

export const NUMERIC = ["monetary", "float", "int", "percent", "ratio", "days"];
export const DETAIL_KINDS = ["detail", "opening", "closing"];

/** A value of the report, formatted for its column type. */
export function formatValue(value, type, { digits, currencyId = false, rounding = false } = {}) {
    if (value === undefined || value === null || value === false || value === "") {
        return "";
    }
    switch (type) {
        case "monetary":
            if (rounding) {
                // in units, thousands or millions, without decimals: "12,345 K $"
                let amount = formatFloat(value / rounding.factor, { digits: [16, 0] });
                if (rounding.suffix) {
                    amount = `${amount} ${rounding.suffix}`;
                }
                const currency = getCurrency(currencyId);
                if (!currency) {
                    return amount;
                }
                return currency.position === "after" ? `${amount} ${currency.symbol}` : `${currency.symbol} ${amount}`;
            }
            return formatMonetary(value, { currencyId });
        case "float":
            return formatFloat(value, { digits: [16, digits ?? 2] });
        case "int":
            return formatInteger(value);
        case "percent":
            return `${formatFloat(value, { digits: [16, 1] })} %`;
        case "ratio":
            return formatFloat(value, { digits: [16, 2] });
        case "days":
            return _t("%s days", formatFloat(value, { digits: [16, digits ?? 1] }));
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

