import { Component, useState, onWillStart } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { customizerState, fieldsInView } from "./customizer_state";

const NEEDS_RELATION = ["many2one", "many2many"];
const NEEDS_SELECTION = ["selection"];

/** A glyph per field type, so the picker reads at a glance. */
export const TYPE_ICONS = {
    char: "fa-font",
    text: "fa-align-left",
    html: "fa-file-text-o",
    integer: "fa-hashtag",
    float: "fa-calculator",
    monetary: "fa-money",
    boolean: "fa-check-square-o",
    date: "fa-calendar",
    datetime: "fa-clock-o",
    selection: "fa-list-ul",
    many2one: "fa-link",
    many2many: "fa-tags",
    binary: "fa-paperclip",
};

/** Turn a label into a legal technical name; the server cleans it again anyway. */
function slugify(label) {
    return (label || "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "")
        .slice(0, 60);
}

export class AddFieldDialog extends Component {
    static template = "om_pen.AddFieldDialog";
    static components = { Dialog };
    static props = {
        close: { type: Function },
        onPicked: { type: Function },
        // when set, the dialog works against an embedded view of an x2many rather than
        // against the view itself, so the fields offered are the comodel's
        target: { type: Object, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            mode: "new", // a new field is what people come here for most of the time
            existing: "",
            search: "",
            label: "",
            name: "", // the part after x_
            nameTouched: false,
            ttype: "char",
            relation: "",
            // a related path, built one hop at a time: each entry is the field chosen at
            // that level, and `steps` holds the choices offered for the next one
            path: [],
            steps: [],
            pathTarget: null,
            selection: "",
            types: [],
            models: [],
            targetFields: null,
            busy: false,
        });

        onWillStart(async () => {
            this.state.types = await this.orm.call("om.pen.view", "field_types", []);
            this.state.models = await this.orm.searchRead("ir.model", [], ["model", "name"], {
                order: "name",
            });
            this.state.steps = [
                await this.orm.call("om.pen.view", "related_steps", [this.model]),
            ];
            if (this.props.target) {
                this.state.targetFields = await this.orm.call(
                    this.props.target.model, "fields_get", [],
                    { attributes: ["string", "type"] }
                );
            }
        });
    }

    get model() {
        return this.props.target?.model || customizerState.config.resModel;
    }

    get icons() {
        return TYPE_ICONS;
    }

    /** Fields on offer, filtered by the search. */
    get availableFields() {
        // an embedded view offers every field of the comodel; the fields already in it
        // are not known here, and adding a duplicate is refused by the server
        const shown = new Set(this.props.target ? [] : fieldsInView());
        const needle = this.state.search.trim().toLowerCase();
        return Object.entries(this.state.targetFields || customizerState.fields)
            .filter(([name]) => !shown.has(name))
            .map(([name, info]) => ({ name, string: info.string || name, type: info.type }))
            .filter(
                (field) =>
                    !needle ||
                    field.string.toLowerCase().includes(needle) ||
                    field.name.toLowerCase().includes(needle)
            )
            .sort((a, b) => a.string.localeCompare(b.string))
            .slice(0, 60);
    }

    /** Clicking the row that is already picked lets go of it again. */
    toggleExisting(name) {
        this.state.existing = this.state.existing === name ? "" : name;
    }

    /** The label of the field currently picked, from whichever model is in play. */
    get pickedLabel() {
        const fields = this.state.targetFields || customizerState.fields;
        return fields[this.state.existing]?.string || this.state.existing;
    }

    // ------------------------------------------------------------------
    // related path
    // ------------------------------------------------------------------

    get relatedPath() {
        return this.state.path.join(".");
    }

    /** Choose the field at one level, dropping whatever was chosen below it. */
    async pickStep(level, name) {
        this.state.path = [...this.state.path.slice(0, level), name];
        this.state.steps = this.state.steps.slice(0, level + 1);
        this.state.pathTarget = null;

        const hop = this.state.steps[level].find((step) => step.name === name);
        if (hop) {
            // load both before showing the next select, otherwise it renders with the
            // links but without the plain fields, and a pick made in that window misses
            const [steps, leafFields] = await Promise.all([
                this.orm.call("om.pen.view", "related_steps", [hop.comodel]),
                this.orm.call(hop.comodel, "fields_get", [], {
                    attributes: ["string", "type"],
                }),
            ]);
            this.state.leafFields = leafFields;
            this.state.steps.push(steps);
        }
        await this.describeTarget();
    }

    /** Ask the server what the path lands on, so the user sees it before creating. */
    async describeTarget() {
        if (this.state.path.length < 2) {
            this.state.pathTarget = null;
            return;
        }
        try {
            this.state.pathTarget = await this.orm.call(
                "om.pen.view", "related_target", [this.model, this.relatedPath]
            );
            if (!this.state.label) {
                this.state.label = this.state.pathTarget.string;
                this.onLabelInput();
            }
        } catch {
            this.state.pathTarget = null;
        }
    }

    get leafChoices() {
        const fields = this.state.leafFields || {};
        return Object.entries(fields)
            .map(([name, info]) => ({ name, string: info.string || name, type: info.type }))
            .sort((a, b) => a.string.localeCompare(b.string));
    }

    get needsRelation() {
        return NEEDS_RELATION.includes(this.state.ttype);
    }

    get needsSelection() {
        return NEEDS_SELECTION.includes(this.state.ttype);
    }

    /** The name that will actually be created, prefix included. */
    get technicalName() {
        return "x_" + (this.state.name || slugify(this.state.label) || "");
    }

    onLabelInput() {
        // the technical name follows the label until the user takes it over
        if (!this.state.nameTouched) {
            this.state.name = slugify(this.state.label);
        }
    }

    onNameInput() {
        this.state.nameTouched = true;
    }

    resetName() {
        this.state.nameTouched = false;
        this.state.name = slugify(this.state.label);
    }

    get canConfirm() {
        if (this.state.busy) {
            return false;
        }
        if (this.state.mode === "existing") {
            return Boolean(this.state.existing);
        }
        if (this.state.mode === "related") {
            return Boolean(this.state.pathTarget) && Boolean(this.state.label.trim());
        }
        if (!this.state.label.trim() || this.technicalName === "x_") {
            return false;
        }
        if (this.needsRelation && !this.state.relation.trim()) {
            return false;
        }
        return !this.needsSelection || Boolean(this.state.selection.trim());
    }

    async confirm() {
        this.state.busy = true;
        try {
            let fieldName = this.state.existing;
            if (this.state.mode === "related") {
                fieldName = await this.orm.call("om.pen.view", "create_field", [
                    this.model,
                    {
                        field_description: this.state.label,
                        name: this.technicalName,
                        related: this.relatedPath,
                    },
                ]);
            } else if (this.state.mode === "new") {
                fieldName = await this.orm.call("om.pen.view", "create_field", [
                    this.model,
                    {
                        field_description: this.state.label,
                        name: this.technicalName,
                        ttype: this.state.ttype,
                        relation: this.state.relation,
                        selection: this.state.selection,
                    },
                ]);
            }
            if (!fieldName) {
                this.notification.add("Pick a field first.", { type: "warning" });
                return;
            }
            this.props.onPicked(fieldName);
            this.props.close();
        } finally {
            this.state.busy = false;
        }
    }
}
