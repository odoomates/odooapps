/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { sprintf } from "@web/core/utils/strings";
import spreadsheet from "@spreadsheet/o_spreadsheet/o_spreadsheet_extended";
import { ServerData } from "@spreadsheet/data_sources/server_data";
import { toServerDateString } from "@spreadsheet/helpers/helpers";

const { functionRegistry, uiPluginRegistry } = spreadsheet.registries;
const { args, toBoolean, toJsDate, toString } = spreadsheet.helpers;

const DATA_SOURCE_ID = "OM_ACCOUNTING_BALANCES";
// the day 0 of the spreadsheets
const SPREADSHEET_EPOCH = Date.UTC(1899, 11, 30);

/**
 * The balances of the account types, fetched in batches like the accounting formulas of Odoo
 */
class OmAccountingDataSource {
    constructor(services) {
        this.serverData = new ServerData(services.orm, {
            whenDataIsFetched: () => services.notify(),
        });
    }

    getBalance(accountTypes, dateFrom, dateTo, includeUnposted) {
        return this.serverData.batch.get("account.move.line", "om_spreadsheet_fetch_balance", {
            account_types: accountTypes,
            date_from: dateFrom,
            date_to: dateTo,
            include_unposted: includeUnposted,
        }).balance;
    }
}

/**
 * The balances of the account types over any period, for the companies selected in the company switcher, and the
 * dates of the date filters. The accounting formulas of Odoo read one company only, over a year, a quarter or a
 * month; ODOO.FILTER.VALUE of Odoo 16 gives the text of a date filter, not its dates.
 */
class OmAccountingPlugin extends spreadsheet.UIPlugin {
    constructor(getters, history, dispatch, config) {
        super(getters, history, dispatch, config);
        this.dataSources = config.dataSources;
        if (this.dataSources) {
            this.dataSources.add(DATA_SOURCE_ID, OmAccountingDataSource);
        }
    }

    getOmAccountBalance(accountTypes, dateFrom, dateTo, includeUnposted) {
        return (
            this.dataSources &&
            this.dataSources
                .get(DATA_SOURCE_ID)
                .getBalance(accountTypes, dateFrom, dateTo, includeUnposted)
        );
    }

    /**
     * @param {string} label the label of a date filter
     * @returns {{start: number, end: number} | undefined} the first and the last day of its period, as spreadsheet
     *  dates, or undefined when it is not set
     */
    getOmFilterPeriod(label) {
        const filter = this.getters
            .getGlobalFilters()
            .find((globalFilter) => globalFilter.label === label && globalFilter.type === "date");
        if (!filter) {
            throw new Error(sprintf(_t("There is no date filter named %s."), label));
        }
        const domain = this.getters.getGlobalFilterDomain(filter.id, { chain: "date", type: "date" });
        const period = {};
        for (const term of domain.toList()) {
            if (Array.isArray(term) && term[0] === "date") {
                const day = toSpreadsheetDate(term[2]);
                if (term[1] === ">=") {
                    period.start = day;
                } else if (term[1] === "<=") {
                    period.end = day;
                }
            }
        }
        return period.start !== undefined && period.end !== undefined ? period : undefined;
    }
}
OmAccountingPlugin.getters = ["getOmAccountBalance", "getOmFilterPeriod"];

uiPluginRegistry.add("omAccountingBalances", OmAccountingPlugin);

function toSpreadsheetDate(serverDate) {
    const [year, month, day] = serverDate.slice(0, 10).split("-").map(Number);
    return Math.round((Date.UTC(year, month - 1, day) - SPREADSHEET_EPOCH) / 86400000);
}

function toServerDate(value) {
    if (value === undefined || value === null || value === "") {
        return false;
    }
    return toServerDateString(toJsDate(value));
}

functionRegistry.add("OM.ACCOUNT.BALANCE", {
    description: _t(
        "Get the balance of the accounts of the given types over a period, for the selected companies."
    ),
    args: args(`
        account_types (string) ${_t('The account types, separated by a comma, e.g. "income,income_other".')}
        date_from (date, optional) ${_t("The first day. Empty: from the beginning.")}
        date_to (date, optional) ${_t("The last day. Empty: up to now.")}
        include_unposted (boolean, default=FALSE) ${_t("Set to TRUE to include unposted entries.")}
    `),
    returns: ["NUMBER"],
    compute: function (accountTypes, dateFrom = "", dateTo = "", includeUnposted = false) {
        const types = toString(accountTypes)
            .split(",")
            .map((type) => type.trim())
            .filter(Boolean)
            .sort();
        if (!types.length) {
            throw new Error(_t("Give at least one account type."));
        }
        return this.getters.getOmAccountBalance(
            types,
            toServerDate(dateFrom),
            toServerDate(dateTo),
            toBoolean(includeUnposted)
        );
    },
    computeFormat: function () {
        return this.getters.getCompanyCurrencyFormat(null) || "#,##0.00";
    },
});

functionRegistry.add("OM.FILTER.START", {
    description: _t("The first day of the period of a date filter, empty when the filter is not set."),
    args: args(`
        filter_name (string) ${_t("The label of the date filter.")}
    `),
    returns: ["DATE"],
    compute: function (filterName) {
        const period = this.getters.getOmFilterPeriod(toString(filterName));
        return period ? period.start : "";
    },
    computeFormat: () => "mm/dd/yyyy",
});

functionRegistry.add("OM.FILTER.END", {
    description: _t("The last day of the period of a date filter, empty when the filter is not set."),
    args: args(`
        filter_name (string) ${_t("The label of the date filter.")}
    `),
    returns: ["DATE"],
    compute: function (filterName) {
        const period = this.getters.getOmFilterPeriod(toString(filterName));
        return period ? period.end : "";
    },
    computeFormat: () => "mm/dd/yyyy",
});
