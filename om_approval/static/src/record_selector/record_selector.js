/** @odoo-module **/

import { Component, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { TagsList } from "@web/views/fields/many2many_tags/tags_list";
import { Many2XAutocomplete } from "@web/views/fields/relational_utils";

/**
 * A record, or several, chosen by their name outside a form view, as the record selectors of the later versions
 * of Odoo do: the designer chooses a group, a company, a currency, the people approving.
 */
export class ApprovalRecordSelector extends Component {
    static template = "om_approval.RecordSelector";
    static components = { Many2XAutocomplete, TagsList };
    static props = {
        resModel: String,
        update: Function,
        resId: { type: [Number, Boolean], optional: true },
        resIds: { type: Array, optional: true },
        multi: { type: Boolean, optional: true },
        domain: { type: Array, optional: true },
        placeholder: { type: String, optional: true },
    };
    static defaultProps = { domain: [], placeholder: "" };

    setup() {
        this.orm = useService("orm");
        // the names of the records shown, by id
        this.names = {};
        onWillStart(() => this.loadNames(this.props));
        onWillUpdateProps((nextProps) => this.loadNames(nextProps));
    }

    ids(props = this.props) {
        if (props.multi) {
            return props.resIds || [];
        }
        return props.resId ? [props.resId] : [];
    }

    async loadNames(props) {
        const missing = this.ids(props).filter((id) => !(id in this.names));
        if (missing.length) {
            for (const [id, name] of await this.orm.call(props.resModel, "name_get", [missing])) {
                this.names[id] = name;
            }
        }
    }

    get tags() {
        return this.ids().map((id) => ({
            id,
            text: this.names[id] || "",
            onDelete: () => this.props.update(this.ids().filter((other) => other !== id)),
        }));
    }

    get value() {
        return this.props.multi || !this.props.resId ? "" : this.names[this.props.resId] || "";
    }

    getDomain() {
        return this.props.multi ? [...this.props.domain, ["id", "not in", this.ids()]] : this.props.domain;
    }

    /** What the autocomplete chose: records with their name, or nothing when its input is emptied. */
    onUpdate(records) {
        if (!records || !records.length) {
            if (!this.props.multi) {
                this.props.update(false);
            }
            return;
        }
        for (const record of records) {
            if (record.name) {
                this.names[record.id] = record.name;
            }
        }
        if (this.props.multi) {
            const ids = this.ids();
            this.props.update([...ids, ...records.map((record) => record.id).filter((id) => !ids.includes(id))]);
        } else {
            this.props.update(records[0].id);
        }
    }
}
