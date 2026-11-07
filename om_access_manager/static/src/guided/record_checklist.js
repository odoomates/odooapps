import { Component, onWillStart, onWillUpdateProps, proxy, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const LIMIT = 40;

/**
 * Records to pick by ticking them: those chosen on top, then a search and the
 * matching records with a box each. Easier than typing names one by one.
 */
export class RecordChecklist extends Component {
    static template = "om_access_manager.RecordChecklist";
    props = useProps({
        resModel: t.string(),
        ids: t.array(),
        update: t.function(),
    });

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ search: "", found: [], names: {}, more: false });
        onWillStart(() => this.load(this.props));
        onWillUpdateProps((next) => {
            if (next.resModel !== this.props.resModel) {
                this.state.search = "";
                return this.load(next);
            }
            return this.loadNames(next);
        });
    }

    async load(props) {
        const found = await this.orm.call(props.resModel, "name_search", [], {
            name: this.state.search, limit: LIMIT + 1,
        });
        this.state.more = found.length > LIMIT;
        this.state.found = found.slice(0, LIMIT).map(([id, name]) => ({ id, name }));
        for (const record of this.state.found) {
            this.state.names[record.id] = record.name;
        }
        await this.loadNames(props);
    }

    async loadNames(props) {
        const missing = props.ids.filter((id) => !(id in this.state.names));
        if (missing.length) {
            const records = await this.orm.read(props.resModel, missing, ["display_name"]);
            for (const record of records) {
                this.state.names[record.id] = record.display_name;
            }
        }
    }

    get chosen() {
        return this.props.ids.map((id) => ({ id, name: this.state.names[id] || `#${id}` }));
    }

    get others() {
        const chosen = new Set(this.props.ids);
        return this.state.found.filter((record) => !chosen.has(record.id));
    }

    onSearch(ev) {
        this.state.search = ev.target.value;
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.load(this.props), 250);
    }

    toggle(record, on) {
        this.state.names[record.id] = record.name;
        const ids = on ? [...this.props.ids, record.id] : this.props.ids.filter((id) => id !== record.id);
        return this.props.update(ids);
    }
}
