import { proxy } from "@odoo/owl";

/**
 * Shared state of customize mode.
 *
 * A plain reactive object rather than a store, so the navbar button, the overlay and
 * the panel all render from one source without talking to each other. It lives apart
 * from the service so that the View patch can publish into it without importing the
 * service.
 */
export const customizerState = proxy({
    active: false,
    selected: null, // technical name of the field being edited
    shownLabel: "", // the caption the selected field showed where it was clicked
    adding: null, // technical name of a field waiting to be placed on the view
    placement: "after", // where the held field goes relative to the one clicked
    saving: false,
    dirty: false, // the panel holds edits that have not been applied

    // published by the View patch on every view load
    current: null, // { resModel, viewId, viewType, viewArch }

    // loaded when customize mode is switched on
    config: null, // the `current` that was frozen when mode was enabled
    fields: {}, // fields_get of the model
    rules: {}, // field name -> saved rule
    pages: [], // notebook pages this customization added
    subviews: [], // x2many fields on this view that carry an embedded list or form
    broken: false, // the generated view no longer matches the view it extends
    hasDraft: false, // there are changes that nobody else can see yet
    draftCount: 0,
    draftInvalid: false, // the draft cannot be published as it stands
    actions: {}, // create_ok, edit_ok, ...
});

/** Only form and list views are customizable for now. */
export const CUSTOMIZABLE_VIEW_TYPES = ["form", "list"];

/** Reflect placement mode on the body, so the CSS can retheme the drop targets. */
export function setPlacing(placing) {
    document.body.classList.toggle("o_om_pen_placing", placing);
}

export function setCustomizeActive(active) {
    customizerState.active = active;
    customizerState.selected = null;
    customizerState.adding = null;
    customizerState.dirty = false;
    document.body.classList.toggle("o_om_pen_active", active);
    setPlacing(false);
}

/** Technical names of the fields the current view already shows. */
export function fieldsInView() {
    const arch = customizerState.config?.viewArch;
    if (!arch) {
        return [];
    }
    return [...new Set([...arch.querySelectorAll("field[name]")].map((n) => n.getAttribute("name")))];
}

/** Read the options already carried by a field node in the live arch. */
export function archOptions(fieldName) {
    const arch = customizerState.config?.viewArch;
    if (!arch) {
        return "{}";
    }
    const node = arch.querySelector(`field[name="${CSS.escape(fieldName)}"]`);
    return node?.getAttribute("options") || "{}";
}

const bindings = new WeakMap();

/**
 * A two-way binding on `obj[key]` for t-model, which takes a signal: a function that
 * reads the value, with a `set` method that writes it. Reading goes through the
 * object, so a reactive object stays reactive. The same function is returned for the
 * same object and key, so a render does not see a new binding each time.
 */
export function bind(obj, key) {
    let keys = bindings.get(obj);
    if (!keys) {
        keys = new Map();
        bindings.set(obj, keys);
    }
    let binding = keys.get(key);
    if (!binding) {
        binding = () => obj[key];
        binding.set = (value) => {
            obj[key] = value;
        };
        keys.set(key, binding);
    }
    return binding;
}
