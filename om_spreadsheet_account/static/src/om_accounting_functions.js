import { _t } from "@web/core/l10n/translation";
import * as spreadsheet from "@odoo/o-spreadsheet";
import { EvaluationError } from "@odoo/o-spreadsheet";
import { OdooEvaluationPlugin } from "@spreadsheet/plugins";
import { toServerDateString } from "@spreadsheet/helpers/helpers";
import { computeFormatFromCurrency } from "@spreadsheet/currency/helpers";

const { functionRegistry, evaluationPluginRegistry } = spreadsheet.registries;
const { arg, toBoolean, toJsDate, toString } = spreadsheet.helpers;

/**
 * The balances of the account types over any period, for the companies selected in the company switcher. The
 * accounting formulas of Odoo read one company only, over a year, a quarter, a month or a fiscal year to date.
 */
export class OmAccountingPlugin extends OdooEvaluationPlugin {
    static getters = /** @type {const} */ (["getOmAccountBalance"]);

    /**
     * @param {string[]} accountTypes
     * @param {string | false} dateFrom first day, or false from the beginning
     * @param {string | false} dateTo last day, or false up to now
     * @param {boolean} includeUnposted
     * @returns {number}
     */
    getOmAccountBalance(accountTypes, dateFrom, dateTo, includeUnposted) {
        const result = this.getters.getServerData().batch.get(
            "account.move.line",
            "om_spreadsheet_fetch_balance",
            {
                account_types: accountTypes,
                date_from: dateFrom,
                date_to: dateTo,
                include_unposted: includeUnposted,
            }
        );
        return result.balance;
    }
}

evaluationPluginRegistry.add("omAccountingBalances", OmAccountingPlugin);

function toServerDate(value, locale) {
    if (value?.value === undefined || value.value === null || value.value === "") {
        return false;
    }
    return toServerDateString(toJsDate(value, locale));
}

functionRegistry.add("OM.ACCOUNT.BALANCE", {
    description: _t(
        "Get the balance of the accounts of the given types over a period, for the selected companies."
    ),
    args: [
        arg(
            "account_types (string)",
            _t('The account types, separated by a comma, e.g. "income,income_other".')
        ),
        arg("date_from (date, optional)", _t("The first day. Empty: from the beginning.")),
        arg("date_to (date, optional)", _t("The last day. Empty: up to now.")),
        arg(
            "include_unposted (boolean, default=FALSE)",
            _t("Set to TRUE to include unposted entries.")
        ),
    ],
    category: "Odoo",
    returns: ["NUMBER"],
    compute: function (
        accountTypes,
        dateFrom = { value: "" },
        dateTo = { value: "" },
        includeUnposted = { value: false }
    ) {
        const types = toString(accountTypes)
            .split(",")
            .map((type) => type.trim())
            .filter(Boolean)
            .sort();
        if (!types.length) {
            return new EvaluationError(_t("Give at least one account type."));
        }
        const balance = this.getters.getOmAccountBalance(
            types,
            toServerDate(dateFrom, this.locale),
            toServerDate(dateTo, this.locale),
            toBoolean(includeUnposted)
        );
        const currency = this.getters.getCompanyCurrency(null);
        return {
            value: balance,
            format: (currency && computeFormatFromCurrency(currency)) || "#,##0.00",
        };
    },
});
