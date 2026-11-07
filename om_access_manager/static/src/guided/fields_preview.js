import { Component, onMounted, onPatched, onWillStart, onWillUnmount, signal, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { View } from "@web/views/view";

// invisible for good: the technical fields of a form, never shown to anyone
const ALWAYS = new Set(["1", "True", "true"]);
// what holds fields; the rest (banners, badges, buttons) only shows messages
const HOLDERS = new Set(["field", "label", "group", "page", "notebook", "separator"]);

/**
 * The form with what its conditions hide shown in place: every invisible="..." with a
 * condition (a state, a value) dropped, and marked, but those of the lines inside an
 * x2many (each line has its own) and the buttons.
 */
export function showConditional(arch) {
    const doc = new DOMParser().parseFromString(arch, "text/xml");
    for (const node of doc.querySelectorAll("[invisible]")) {
        const value = (node.getAttribute("invisible") || "").trim();
        const css = node.getAttribute("class") || "";
        const holder = HOLDERS.has(node.tagName)
            || (["div", "span"].includes(node.tagName) && !/\balert\b|\bbadge\b/.test(css)
                && node.querySelector("field:not([invisible='1']):not([invisible='True'])"));
        if (ALWAYS.has(value) || !holder) {
            continue;
        }
        let parent = node.parentElement;
        let nested = false;
        while (parent && parent !== doc.documentElement) {
            if (parent.tagName === "field") {
                nested = true;
                break;
            }
            parent = parent.parentElement;
        }
        if (nested) {
            continue;
        }
        node.removeAttribute("invisible");
        node.setAttribute("class", `${node.getAttribute("class") || ""} o_om_conditional`.trim());
    }
    return new XMLSerializer().serializeToString(doc);
}

// a click moves a field to the next: normal, read only, hidden, normal again
export const FIELD_CYCLE = { keep: "readonly", readonly: "hide", hide: "keep" };

/**
 * The form of a data as its users see it, drawn by Odoo itself (read only, on one of its
 * records), to set its fields on: a click on a field or its label moves it to read only,
 * hidden, and back. Nothing on it runs: every click is caught, but those on the tabs.
 */
export class FieldsPreview extends Component {
    static template = "om_access_manager.FieldsPreview";
    static components = { View };
    props = useProps({
        entry: t.object(),
        onField: t.function(),
        search: t.string().optional(""),
        showAll: t.boolean().optional(false),
    });

    setup() {
        this.root = signal.ref();
        this.viewService = useService("view");
        const entry = this.props.entry;
        // made once: the form is not loaded again when a field changes
        this.viewProps = {
            type: "form",
            resModel: entry.model,
            resId: entry.sample_id || false,
            viewId: entry.form_view_id || false,
            readonly: true,
            preventEdit: true,
            preventCreate: true,
            display: { controlPanel: false },
            context: { ...(entry.form_context || {}), create: false, edit: false },
        };
        if (this.props.showAll) {
            // the form as loaded for the screen, its conditions dropped: given to the view as is
            onWillStart(async () => {
                const result = await this.viewService.loadViews({
                    resModel: entry.model,
                    context: this.viewProps.context,
                    views: [[entry.form_view_id || false, "form"]],
                }, {});
                Object.assign(this.viewProps, {
                    arch: showConditional(result.views.form.arch),
                    fields: result.fields,
                    relatedModels: result.relatedModels,
                });
            });
        }
        this.tags = { readonly: _t("read only"), hide: _t("hidden"), required: _t("required"), condition: _t("when...") };
        onMounted(() => {
            this.decorate();
            // the form draws again (tabs, loading): its fields marked again
            this.observer = new MutationObserver(() => this.scheduleDecorate());
            this.observer.observe(this.root(), { childList: true, subtree: true });
        });
        onPatched(() => this.decorate());
        onWillUnmount(() => this.observer?.disconnect());
    }

    get fieldsByName() {
        return Object.fromEntries(this.props.entry.fields.map((field) => [field.name, field]));
    }

    scheduleDecorate() {
        if (!this.pending) {
            this.pending = requestAnimationFrame(() => {
                this.pending = null;
                this.decorate();
            });
        }
    }

    /** The field of an element of the form: a field widget, or the label of one. */
    fieldOf(element) {
        const widget = element.closest(".o_field_widget[name]");
        if (widget && !widget.parentElement.closest(".o_field_x2many .o_data_row, .o_field_x2many tr")) {
            return widget.getAttribute("name");
        }
        const label = element.closest("label.o_form_label[for]");
        if (label) {
            return label.getAttribute("for").replace(/_\d+$/, "");
        }
        return null;
    }

    stateOf(field) {
        if (field.condition) {
            return "condition";
        }
        return field.mode === "keep" ? "" : field.mode;
    }

    /** Each field of the form marked with its state; the observer is paused meanwhile. */
    decorate() {
        const root = this.root();
        if (!root) {
            return;
        }
        this.observer?.disconnect();
        const fields = this.fieldsByName;
        const search = (this.props.search || "").trim().toLowerCase();
        const elements = [...root.querySelectorAll(".o_form_sheet .o_field_widget[name], .o_form_sheet label.o_form_label[for]")];
        for (const element of elements) {
            const name = element.matches(".o_field_widget")
                ? element.getAttribute("name") : element.getAttribute("for").replace(/_\d+$/, "");
            const field = fields[name];
            const state = field ? this.stateOf(field) : "";
            if ((element.dataset.omState || "") !== state) {
                element.dataset.omState = state;
            }
            const tag = state ? this.tags[state] : "";
            if (element.matches("label") && (element.dataset.omTag || "") !== tag) {
                element.dataset.omTag = tag;
            }
            const match = Boolean(search && field && field.label.toLowerCase().includes(search));
            element.classList.toggle("o_om_field_match", match);
            element.classList.toggle("o_om_field_known", Boolean(field));
        }
        this.observer?.observe(root, { childList: true, subtree: true });
    }

    onClick(ev) {
        // the tabs open, as on the screen; nothing else of the form runs
        if (ev.target.closest(".o_notebook_headers .nav-link")) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        const name = this.fieldOf(ev.target);
        const field = name && this.fieldsByName[name];
        if (field) {
            this.props.onField(field);
        }
    }
}
