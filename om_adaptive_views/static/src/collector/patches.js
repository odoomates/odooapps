import { patch } from "@web/core/utils/patch";
import { Record } from "@web/model/relational_model/record";
import { SearchModel } from "@web/search/search_model";
import { ListRenderer } from "@web/views/list/list_renderer";
import { NavBar } from "@web/webclient/navbar/navbar";

import { count, isLearning } from "./collector";

function config(env) {
    const conf = env?.config || {};
    return {
        viewId: Number.isInteger(conf.viewId) ? conf.viewId : 0,
        actionId: Number.isInteger(conf.actionId) ? conf.actionId : 0,
        viewType: conf.viewType,
    };
}

/** A form saved: which fields were changed, by name only. */
patch(Record.prototype, {
    async _save() {
        const tracked = isLearning() && this === this.model.root && config(this.model.env).viewType === "form";
        const creating = !this.resId;
        const changed = tracked ? Object.keys(this._getChanges()).filter((name) => name !== "id") : [];
        const result = await super._save(...arguments);
        // leaving a form saves it even when nothing changed: only real saves count
        if (tracked && result && (changed.length || creating)) {
            const { viewId } = config(this.model.env);
            count("save", this.resModel, { viewId });
            for (const name of changed) {
                count("edit", this.resModel, { element: name, viewId });
            }
        }
        return result;
    },
});

/** An action opened, and the filters and group-bys switched on by hand in it. */
patch(SearchModel.prototype, {
    async load() {
        const result = await super.load(...arguments);
        // a visit is an action opened on its records, not a single record opened from a link
        const { actionId, viewType } = config(this.env);
        if (actionId && this.resModel && viewType && viewType !== "form") {
            count("visit", this.resModel, { actionId });
        }
        return result;
    },

    toggleSearchItem(searchItemId) {
        const item = this.searchItems[searchItemId];
        const wasActive = this.query.some((q) => q.searchItemId === searchItemId);
        const result = super.toggleSearchItem(...arguments);
        const { actionId } = config(this.env);
        // once per visit: switching a filter off and on again is still one use
        this.omCountedFilters ||= new Set();
        const counted = ["filter", "groupBy"].includes(item?.type);
        if (!wasActive && counted && item.name && actionId && !this.omCountedFilters.has(item.name)) {
            this.omCountedFilters.add(item.name);
            count("filter", this.resModel, { element: item.name, actionId });
        }
        return result;
    },
});

/** Optional columns switched on or off. */
patch(ListRenderer.prototype, {
    async toggleOptionalField(fieldName) {
        const result = await super.toggleOptionalField(...arguments);
        const { viewId } = config(this.env);
        const shown = Boolean(this.optionalActiveFields[fieldName]);
        count(shown ? "column_on" : "column_off", this.props.list.resModel, { element: fieldName, viewId });
        return result;
    },
});

/** A menu opened from the navbar: the apps menu, the app's menus, or the phone menu. */
function countMenu(menu) {
    const id = typeof menu === "number" ? menu : menu?.id;
    if (id) {
        count("menu", "ir.ui.menu", { element: String(id) });
    }
}

patch(NavBar.prototype, {
    onNavBarDropdownItemSelection(menu) {
        countMenu(menu);
        return super.onNavBarDropdownItemSelection(...arguments);
    },

    _onMenuClicked(menu) {
        countMenu(menu);
        return super._onMenuClicked(...arguments);
    },
});
