import { _t } from "@web/core/l10n/translation";

/**
 * The live preview of a field being dragged onto a view.
 *
 * While dragging, a ghost slot - a label and an input, drawn dashed - sits exactly
 * where the field will land, and follows the pointer. Dropping a brand new field turns
 * that slot into a small editor in place, so the label is typed where the field goes
 * rather than in a dialog somewhere else.
 *
 * Plain DOM, not a component: the form is rendered by the web client, outside the
 * customizer, and the slot has to live among its nodes. Everything added here is
 * removed again before the view is reloaded, so the renderer never meets it.
 */
export class DropPreview {
    constructor() {
        this.nodes = [];
        this.key = null;
        this.floating = null;
        this.editing = false;
    }

    /** Is this element part of the preview, so the pointer over it changes nothing? */
    contains(element) {
        return Boolean(element?.closest?.(".o_om_pen_ghost, .o_om_pen_ghost_float"));
    }

    /**
     * Draw the slot at `target`, as returned by the overlay's dropTargetAt.
     *
     * A notebook tab cannot hold a slot - its page is usually not even on screen - so
     * the tab itself lights up instead.
     */
    show(target, { label, icon }) {
        const key = target ? `${target.kind || "field"}:${target.name || target.pageName}:${target.position || ""}` : null;
        if (key === this.key) {
            return;
        }
        this.clear();
        this.key = key;
        if (!target) {
            return;
        }
        if (target.kind === "page") {
            target.node.classList.add("o_om_pen_drop_into");
            this.nodes.push({ unmark: target.node });
            return;
        }
        const node = target.node;
        if (node.matches("th, td")) {
            // a list: a line down the side of the column header the field lands next to
            const header = node.matches("th")
                ? node
                : node.closest("table")?.querySelector(`th[data-name="${CSS.escape(target.name)}"]`);
            if (header) {
                const mark = `o_om_pen_col_${target.position}`;
                header.classList.add(mark);
                header.dataset.omPenDrop = label;
                this.nodes.push({ unmark: header, mark });
                return;
            }
        }
        const cell = node.closest(".o_inner_group > .o_cell");
        if (cell) {
            // a group is a grid of label and input cells: the slot is one more pair
            const labelCell = cell.previousElementSibling?.classList.contains("o_wrap_label")
                ? cell.previousElementSibling
                : null;
            const first = labelCell || cell;
            const anchor = target.position === "before" ? first : cell.nextElementSibling;
            const ghostLabel = this.el("div", "o_cell o_wrap_label o_om_pen_ui o_om_pen_ghost");
            ghostLabel.append(this.el("span", "o_form_label", label));
            const ghostInput = this.el("div", "o_cell o_wrap_input o_om_pen_ui o_om_pen_ghost");
            const box = this.el("div", "o_om_pen_ghost_input");
            box.append(this.el("i", `fa fa-fw ${icon || "fa-plus"} me-1`), this.el("span", "", _t("drops here")));
            ghostInput.append(box);
            cell.parentElement.insertBefore(ghostLabel, anchor);
            cell.parentElement.insertBefore(ghostInput, anchor);
            this.nodes.push(ghostLabel, ghostInput);
            this.labelCell = ghostLabel;
            this.inputCell = ghostInput;
            return;
        }
        // anywhere else - a page body, a list - the slot is a bar of its own
        const bar = this.el("div", "o_om_pen_ui o_om_pen_ghost o_om_pen_ghost_bar");
        const barLabel = this.el("span", "o_om_pen_ghost_bar_label", label);
        const barInput = this.el("span", "o_om_pen_ghost_input");
        barInput.append(this.el("i", `fa fa-fw ${icon || "fa-plus"} me-1`), this.el("span", "", _t("drops here")));
        bar.append(barLabel, barInput);
        node.parentElement.insertBefore(bar, target.position === "before" ? node : node.nextSibling);
        this.nodes.push(bar);
        this.labelCell = barLabel;
        this.inputCell = barInput;
    }

    clear() {
        for (const node of this.nodes) {
            if (node.unmark) {
                node.unmark.classList.remove(node.mark || "o_om_pen_drop_into");
                delete node.unmark.dataset.omPenDrop;
            } else {
                node.remove();
            }
        }
        this.floating?.remove();
        this.nodes = [];
        this.key = null;
        this.floating = null;
        this.labelCell = null;
        this.inputCell = null;
        this.editing = false;
    }

    /**
     * Turn the slot into an editor for a new field and wait for the user.
     *
     * @param {Object} options
     * @param {string} options.typeLabel shown as the input's placeholder
     * @param {boolean} options.needsRelation ask for the model to link to
     * @param {boolean} options.needsSelection ask for the options
     * @param {Array} options.models [{model, name}] offered for a relation
     * @param {DOMRect} [options.anchorRect] where to float the editor when there is
     *     no slot on the form, as on a notebook tab
     * @returns {Promise<Object|null>} {label, relation, selection}, or null if cancelled
     */
    edit({ typeLabel, needsRelation, needsSelection, models, anchorRect }) {
        this.editing = true;
        let labelHost = this.labelCell;
        let inputHost = this.inputCell;
        if (!labelHost) {
            // no slot to type into: float a small card under the tab instead
            const card = this.el("div", "o_om_pen_ui o_om_pen_ghost_float");
            const rect = anchorRect || { left: window.innerWidth / 3, bottom: 160 };
            card.style.left = `${Math.max(8, rect.left)}px`;
            card.style.top = `${rect.bottom + 8}px`;
            labelHost = this.el("div", "mb-2");
            inputHost = this.el("div", "");
            card.append(labelHost, inputHost);
            document.body.append(card);
            this.floating = card;
        }
        labelHost.replaceChildren();
        inputHost.replaceChildren();
        labelHost.classList.add("o_om_pen_ghost_editing");
        inputHost.classList.add("o_om_pen_ghost_editing");

        const label = this.el("input", "form-control form-control-sm");
        label.placeholder = _t("Label of the new field");
        labelHost.append(label);

        const extra = this.el("div", "o_om_pen_ghost_extra");
        let relation = null;
        let selection = null;
        if (needsRelation) {
            relation = this.el("input", "form-control form-control-sm");
            relation.placeholder = _t("Links to, e.g. Contact");
            const listId = `o_om_pen_models_${Date.now()}`;
            relation.setAttribute("list", listId);
            const list = this.el("datalist", "");
            list.id = listId;
            for (const model of models || []) {
                const option = document.createElement("option");
                option.value = model.name;
                option.label = model.model;
                list.append(option);
            }
            extra.append(relation, list);
        } else if (needsSelection) {
            selection = this.el("input", "form-control form-control-sm");
            selection.placeholder = _t("Options: Low, Medium, High");
            extra.append(selection);
        } else {
            extra.append(this.el("span", "o_om_pen_ghost_type", typeLabel));
        }
        const ok = this.el("button", "btn btn-sm btn-primary ms-1");
        ok.type = "button";
        ok.title = _t("Create (Enter)");
        ok.append(this.el("i", "fa fa-check"));
        const cancel = this.el("button", "btn btn-sm btn-light ms-1");
        cancel.type = "button";
        cancel.title = _t("Cancel (Esc)");
        cancel.append(this.el("i", "fa fa-times"));
        const row = this.el("div", "o_om_pen_ghost_row");
        row.append(extra, ok, cancel);
        inputHost.append(row);

        return new Promise((resolve) => {
            const finish = (values) => {
                this.editing = false;
                resolve(values);
            };
            const submit = () => {
                if (!label.value.trim()) {
                    label.focus();
                    label.classList.add("is-invalid");
                    return;
                }
                let model = null;
                if (relation) {
                    const typed = relation.value.trim().toLowerCase();
                    const hit = (models || []).find(
                        (m) => m.name.toLowerCase() === typed || m.model === typed
                    );
                    if (!hit) {
                        relation.focus();
                        relation.classList.add("is-invalid");
                        return;
                    }
                    model = hit.model;
                }
                const options = selection
                    ? selection.value.split(/[,\n]/).map((s) => s.trim()).filter(Boolean)
                    : [];
                if (selection && !options.length) {
                    selection.focus();
                    selection.classList.add("is-invalid");
                    return;
                }
                finish({ label: label.value.trim(), relation: model, selection: options.join("\n") });
            };
            const onKey = (ev) => {
                // the overlay listens on the document for Esc and Ctrl+Enter
                ev.stopPropagation();
                if (ev.key === "Enter") {
                    ev.preventDefault();
                    submit();
                } else if (ev.key === "Escape") {
                    ev.preventDefault();
                    finish(null);
                }
            };
            for (const input of [label, relation, selection].filter(Boolean)) {
                input.addEventListener("keydown", onKey);
                input.addEventListener("input", () => input.classList.remove("is-invalid"));
            }
            ok.addEventListener("click", submit);
            cancel.addEventListener("click", () => finish(null));
            label.focus();
        });
    }

    el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text) {
            node.textContent = text;
        }
        return node;
    }
}
