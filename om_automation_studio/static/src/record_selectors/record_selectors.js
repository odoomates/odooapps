/** @odoo-module **/

import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { AutoComplete } from "@web/core/autocomplete/autocomplete";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

const SEARCH_LIMIT = 8;

/**
 * Odoo 16 has no record selectors: these two have the props of those of
 * later versions, so that the templates of the designer stay the same.
 */
class RecordSearch extends Component {
    setup() {
        this.orm = useService("orm");
        this.source = { options: (request) => this.search(request) };
    }

    async search(request) {
        const found = await this.orm.call(this.props.resModel, "name_search", [], {
            name: request || "",
            args: this.props.domain || [],
            limit: SEARCH_LIMIT,
        });
        return found
            .filter(([id]) => !this.chosenIds().includes(id))
            // AutoComplete gives each option an id of its own: the record's goes in resId
            .map(([id, name]) => ({ resId: id, label: name }));
    }

    async names(ids) {
        if (!ids.length) {
            return {};
        }
        const records = await this.orm.read(this.props.resModel, ids, ["display_name"]);
        return Object.fromEntries(records.map((record) => [record.id, record.display_name]));
    }
}

export class RecordSelector extends RecordSearch {
    static template = "om_automation_studio.RecordSelector";
    static components = { AutoComplete };
    static props = {
        resId: [Number, Boolean],
        resModel: String,
        update: Function,
        domain: { type: Array, optional: true },
        context: { type: Object, optional: true },
        placeholder: { type: String, optional: true },
    };

    setup() {
        super.setup();
        this.state = useState({ name: "" });
        onWillStart(() => this.loadName(this.props.resId));
        onWillUpdateProps((next) => next.resId !== this.props.resId && this.loadName(next.resId));
    }

    chosenIds() {
        return this.props.resId ? [this.props.resId] : [];
    }

    async loadName(resId) {
        this.state.name = resId ? (await this.names([resId]))[resId] || "" : "";
    }

    onSelect(option) {
        this.state.name = option.label;
        this.props.update(option.resId);
    }

    onChange({ inputValue }) {
        if (!inputValue.trim()) {
            this.props.update(false);
        }
    }
}

export class MultiRecordSelector extends RecordSearch {
    static template = "om_automation_studio.MultiRecordSelector";
    static components = { AutoComplete };
    static props = {
        resIds: { type: Array, element: Number },
        resModel: String,
        update: Function,
        domain: { type: Array, optional: true },
        context: { type: Object, optional: true },
        placeholder: { type: String, optional: true },
    };

    setup() {
        super.setup();
        this.placeholder = _t("Add...");
        this.state = useState({ names: {} });
        onWillStart(() => this.loadNames(this.props.resIds));
        onWillUpdateProps((next) => this.loadNames(next.resIds));
    }

    chosenIds() {
        return this.props.resIds;
    }

    async loadNames(resIds) {
        const missing = resIds.filter((id) => !(id in this.state.names));
        Object.assign(this.state.names, await this.names(missing));
    }

    onSelect(option) {
        this.state.names[option.resId] = option.label;
        this.props.update([...this.props.resIds, option.resId]);
    }

    remove(id) {
        this.props.update(this.props.resIds.filter((other) => other !== id));
    }
}
