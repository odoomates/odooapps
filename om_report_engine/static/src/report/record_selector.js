/** @odoo-module **/

import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { AutoComplete } from "@web/core/autocomplete/autocomplete";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

const SEARCH_LIMIT = 8;

/** Records picked as tags, searched by name: `update` receives the list of their ids. */
export class MultiRecordSelector extends Component {
    static template = "om_report_engine.MultiRecordSelector";
    static components = { AutoComplete };
    static props = {
        resModel: String,
        resIds: Array,
        domain: { type: Array, optional: true },
        update: Function,
        placeholder: { type: String, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.names = useState({});
        onWillStart(() => this.loadNames(this.props.resIds));
        onWillUpdateProps((next) => this.loadNames(next.resIds));
    }

    async loadNames(ids) {
        const missing = ids.filter((id) => !(id in this.names));
        if (missing.length) {
            const records = await this.orm.read(this.props.resModel, missing, ["display_name"]);
            for (const record of records) {
                this.names[record.id] = record.display_name;
            }
        }
    }

    get sources() {
        return [{ placeholder: _t("Loading..."), options: (request) => this.search(request) }];
    }

    async search(request) {
        const results = await this.orm.call(this.props.resModel, "name_search", [], {
            name: request,
            args: this.props.domain || [],
            limit: SEARCH_LIMIT,
        });
        return results
            .filter(([id]) => !this.props.resIds.includes(id))
            .map(([id, name]) => ({ value: id, label: name }));
    }

    onSelect(option) {
        this.names[option.value] = option.label;
        this.props.update([...this.props.resIds, option.value]);
    }

    remove(id) {
        this.props.update(this.props.resIds.filter((resId) => resId !== id));
    }
}
