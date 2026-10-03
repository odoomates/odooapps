/** @odoo-module **/

import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { AutoComplete } from "@web/core/autocomplete/autocomplete";
import { useService } from "@web/core/utils/hooks";

const SEARCH_LIMIT = 8;

/**
 * The RecordSelector and MultiRecordSelector of Odoo 17 and later, which Odoo 16 has not: the same props, on top of
 * the AutoComplete of 16. `update` receives the id of the record (false when cleared) or the list of the ids.
 */
class BaseRecordSelector extends Component {
    setup() {
        this.orm = useService("orm");
        this.names = useState({});
        onWillStart(() => this.loadNames(this.ids(this.props)));
        onWillUpdateProps((nextProps) => this.loadNames(this.ids(nextProps)));
    }

    ids(props) {
        return [];
    }

    async loadNames(ids) {
        const missing = ids.filter((id) => !(id in this.names));
        if (!missing.length) {
            return;
        }
        const records = await this.orm.read(this.props.resModel, missing, ["display_name"]);
        for (const record of records) {
            this.names[record.id] = record.display_name;
        }
    }

    get sources() {
        return [{ placeholder: this.env._t("Loading..."), options: (request) => this.search(request) }];
    }

    async search(request) {
        const results = await this.orm.call(this.props.resModel, "name_search", [], {
            name: request,
            args: this.props.domain || [],
            limit: SEARCH_LIMIT,
        });
        const excluded = this.ids(this.props);
        return results
            .filter(([id]) => !excluded.includes(id))
            .map(([id, name]) => ({ value: id, label: name }));
    }
}
BaseRecordSelector.components = { AutoComplete };

export class RecordSelector extends BaseRecordSelector {
    ids(props) {
        return props.resId ? [props.resId] : [];
    }

    get value() {
        return (this.props.resId && this.names[this.props.resId]) || "";
    }

    onSelect(option) {
        this.names[option.value] = option.label;
        this.props.update(option.value);
    }

    onChange({ inputValue }) {
        // the name erased: no record
        if (!inputValue.trim() && this.props.resId) {
            this.props.update(false);
        }
    }
}
RecordSelector.template = "om_account_reconcile.RecordSelector";
RecordSelector.props = {
    resModel: String,
    resId: { type: [Number, Boolean], optional: true },
    domain: { type: Array, optional: true },
    update: Function,
    placeholder: { type: String, optional: true },
};

export class MultiRecordSelector extends BaseRecordSelector {
    ids(props) {
        return props.resIds || [];
    }

    onSelect(option) {
        this.names[option.value] = option.label;
        this.props.update([...this.ids(this.props), option.value]);
    }

    remove(id) {
        this.props.update(this.ids(this.props).filter((resId) => resId !== id));
    }
}
MultiRecordSelector.template = "om_account_reconcile.MultiRecordSelector";
MultiRecordSelector.props = {
    resModel: String,
    resIds: { type: Array, optional: true },
    domain: { type: Array, optional: true },
    update: Function,
    placeholder: { type: String, optional: true },
};
