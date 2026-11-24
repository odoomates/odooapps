import { Component, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { DomainSelectorDialog } from "@web/core/domain_selector_dialog/domain_selector_dialog";

/**
 * The search view, edited as three lists: the fields searched as the user types,
 * the filters, and the group-bys. A search view has nothing to click on a canvas.
 */
export class SearchEditor extends Component {
    static template = "om_pen.SearchEditor";
    props = useProps();

    setup() {
        this.store = this.props.store;
        this.dialog = useService("dialog");
        this.ui = proxy({ editing: null, filterName: "" });
    }

    isInPanel(node) {
        let parent = this.store.node(node.parent);
        const seen = new Set();
        while (parent && !seen.has(parent.id)) {
            seen.add(parent.id);
            if (parent.tag === "searchpanel") {
                return true;
            }
            parent = this.store.node(parent.parent);
        }
        return false;
    }

    get items() {
        return Object.values(this.store.nodes)
            .filter((n) => ["field", "filter", "separator"].includes(n.tag) && !n.owners.length && !this.isInPanel(n))
            .sort((a, b) => a.id - b.id);
    }

    isGroupBy(node) {
        return node.tag === "filter" && /group_by/.test(node.attrs.context || "");
    }

    get searchFields() {
        return this.items.filter((n) => n.tag === "field");
    }

    get filters() {
        return this.items.filter((n) => (n.tag === "filter" && !this.isGroupBy(n)) || n.tag === "separator");
    }

    get groupBys() {
        return this.items.filter((n) => this.isGroupBy(n));
    }

    label(node) {
        if (node.tag === "separator") {
            return "———";
        }
        return this.store.labelOf(node);
    }

    get fields() {
        return Object.values(this.store.view.all_fields).sort((a, b) => a.string.localeCompare(b.string));
    }

    get groupableFields() {
        return this.fields.filter((f) => f.store && !["one2many", "binary", "html", "text"].includes(f.type));
    }

    async moveItem(list, index, delta) {
        const other = list[index + delta];
        if (!other) {
            return;
        }
        await this.store.move(list[index].id, other.id, delta < 0 ? "before" : "after");
    }

    async remove(node) {
        await this.store.remove(node.id);
    }

    startRename(node) {
        this.ui.editing = node.id;
    }

    async rename(node, ev) {
        this.ui.editing = null;
        const value = ev.target.value.trim();
        if (value && value !== this.label(node)) {
            await this.store.setAttrs(node.id, { string: value });
        }
    }

    async addField(ev) {
        const name = ev.target.value;
        ev.target.value = "";
        if (name) {
            await this.store.insert(this.store.rootId, "inside", { kind: "field", name });
        }
    }

    async addGroupBy(ev) {
        const field = ev.target.value;
        ev.target.value = "";
        if (field) {
            await this.store.insert(this.store.rootId, "inside", { kind: "groupby", field });
        }
    }

    async addSeparator() {
        await this.store.insert(this.store.rootId, "inside", { kind: "search_separator" });
    }

    addFilter() {
        this.dialog.add(DomainSelectorDialog, {
            resModel: this.store.info.model,
            domain: "[]",
            isDebugMode: true,
            title: _t("New filter: which records does it keep?"),
            onConfirm: async (domain) => {
                const name = this.ui.filterName.trim() || _t("New Filter");
                this.ui.filterName = "";
                await this.store.insert(this.store.rootId, "inside", { kind: "filter", string: name, domain });
            },
        });
    }

    editDomain(node) {
        this.dialog.add(DomainSelectorDialog, {
            resModel: this.store.info.model,
            domain: node.attrs.domain || "[]",
            isDebugMode: true,
            title: _t("Records kept by %s", this.label(node)),
            onConfirm: (domain) => this.store.setAttrs(node.id, { domain }),
        });
    }
}
