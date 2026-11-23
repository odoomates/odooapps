import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";

/** Ask what the new field is called and, for some kinds, what it links to. */
export class NewFieldDialog extends Component {
    static template = "om_pen.NewFieldDialog";
    static components = { Dialog };
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.state = proxy({
            label: "",
            name: "",
            relation: "",
            relation_field: "",
            selection: "",
            related: "",
            lines: "",
            operation: "count",
            measure: "",
            saving: false,
        });
        this.data = proxy({ models: [], inverses: [], lineFields: [], measures: [], steps: [] });
        onWillStart(async () => {
            if (["many2one", "many2many", "one2many"].includes(this.props.kind)) {
                this.data.models = await this.orm.call("om.pen.studio", "studio_models", []);
            }
            if (this.props.kind === "total") {
                const fields = this.props.fields;
                this.data.lineFields = Object.values(fields).filter((f) =>
                    ["one2many", "many2many"].includes(f.type)
                );
            }
            if (this.props.kind === "related") {
                this.data.steps = await this.orm.call("om.pen.view", "related_steps", [this.props.model]);
            }
        });
    }

    get title() {
        return _t("New %s", this.props.label);
    }

    async onRelationChange(ev) {
        this.state.relation = ev.target.value;
        this.state.relation_field = "";
        if (this.props.kind === "one2many" && this.state.relation) {
            const fields = await this.orm.call(this.state.relation, "fields_get", [], {
                attributes: ["string", "type", "relation"],
            });
            this.data.inverses = Object.entries(fields)
                .filter(([, f]) => f.type === "many2one" && f.relation === this.props.model)
                .map(([name, f]) => ({ name, string: f.string }));
        }
    }

    async onLinesChange(ev) {
        this.state.lines = ev.target.value;
        this.state.measure = "";
        const field = this.props.fields[this.state.lines];
        if (field?.relation) {
            const fields = await this.orm.call(field.relation, "fields_get", [], {
                attributes: ["string", "type"],
            });
            this.data.measures = Object.entries(fields)
                .filter(([, f]) => ["integer", "float", "monetary"].includes(f.type))
                .map(([name, f]) => ({ name, string: f.string }));
        }
    }

    async confirm() {
        const values = { kind: this.props.kind, ...this.state };
        delete values.saving;
        this.state.saving = true;
        try {
            await this.props.onConfirm(values);
            this.props.close();
        } finally {
            this.state.saving = false;
        }
    }
}

/** A field itself: its default value, and for a custom field its label, help and options. */
export class FieldSettingsDialog extends Component {
    static template = "om_pen.FieldSettingsDialog";
    static components = { Dialog };
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ info: null, label: "", help: "", required: false, default: "", options: [] });
        onWillStart(async () => {
            const info = await this.orm.call("om.pen.studio", "studio_field_info", [
                this.props.model,
                this.props.fieldName,
            ]);
            this.state.info = info;
            this.state.label = info.label;
            this.state.help = info.help;
            this.state.required = info.required;
            this.state.default = info.default === null || info.default === undefined ? "" : info.default;
            this.state.options = info.selection.map((o) => ({ ...o }));
        });
    }

    get simpleDefault() {
        return ["char", "text", "integer", "float", "monetary", "boolean", "selection", "date", "datetime"].includes(
            this.state.info?.type
        );
    }

    addOption() {
        this.state.options.push({ value: "", name: "" });
    }

    removeOption(index) {
        this.state.options.splice(index, 1);
    }

    async save() {
        const info = this.state.info;
        const values = {};
        if (this.simpleDefault) {
            let value = this.state.default;
            if (info.type === "boolean") {
                value = Boolean(value);
            } else if (["integer", "float", "monetary"].includes(info.type)) {
                value = value === "" ? null : Number(value);
            }
            values.default = value;
        }
        if (info.custom) {
            values.label = this.state.label;
            values.help = this.state.help;
            values.required = this.state.required;
            if (info.type === "selection") {
                values.selection = this.state.options.filter((o) => o.name.trim());
            }
        }
        await this.orm.call("om.pen.studio", "studio_field_save", [this.props.model, this.props.fieldName, values]);
        await this.props.onSaved?.();
        this.props.close();
    }
}

/** Show what uses a custom field, then delete it. */
export class FieldDeleteDialog extends Component {
    static template = "om_pen.FieldDeleteDialog";
    static components = { Dialog };
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ impact: null, deleting: false });
        onWillStart(async () => {
            this.state.impact = await this.orm.call("om.pen.studio", "studio_field_impact", [
                this.props.model,
                this.props.fieldName,
            ]);
        });
    }

    async confirm() {
        this.state.deleting = true;
        try {
            await this.orm.call("om.pen.studio", "studio_field_delete", [this.props.model, this.props.fieldName]);
            await this.props.onDeleted?.();
            this.props.close();
        } finally {
            this.state.deleting = false;
        }
    }
}

/** A button counting the records linked to this one. */
export class SmartButtonDialog extends Component {
    static template = "om_pen.SmartButtonDialog";
    static components = { Dialog };
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ targets: [], choice: "", label: "", icon: "view_list" });
        this.icons = ["view_list", "description", "shopping_cart", "event_upcoming", "person", "task", "inventory_2", "payments", "article", "star"];
        onWillStart(async () => {
            this.state.targets = await this.orm.call("om.pen.studio", "studio_smart_button_targets", [
                this.props.model,
            ]);
        });
    }

    onChoice(ev) {
        this.state.choice = ev.target.value;
        const target = this.state.targets[Number(this.state.choice)];
        if (target && !this.state.label) {
            this.state.label = target.label.split(" (")[0];
        }
    }

    async confirm() {
        const target = this.state.targets[Number(this.state.choice)];
        if (!target) {
            return;
        }
        await this.props.onConfirm({
            model: target.model,
            field: target.field,
            label: this.state.label,
            icon: this.state.icon,
        });
        this.props.close();
    }
}

/** A button in the form header, setting a field or running a server action. */
export class HeaderButtonDialog extends Component {
    static template = "om_pen.HeaderButtonDialog";
    static components = { Dialog };
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.state = proxy({
            string: "",
            mode: "field",
            field: "",
            value: "",
            action_id: "",
            primary: true,
            confirm: "",
            actions: [],
        });
        onWillStart(async () => {
            this.state.actions = await this.orm.call("om.pen.studio", "studio_actions", [this.props.model]);
        });
    }

    get settableFields() {
        return Object.values(this.props.fields)
            .filter((f) => !f.readonly && ["char", "boolean", "selection", "integer", "float", "date"].includes(f.type))
            .sort((a, b) => a.string.localeCompare(b.string));
    }

    get selectedField() {
        return this.props.fields[this.state.field];
    }

    async confirm() {
        const values = {
            string: this.state.string,
            primary: this.state.primary,
            confirm: this.state.confirm,
        };
        if (this.state.mode === "field") {
            values.field = this.state.field;
            values.value = this.state.value;
        } else {
            values.action_id = Number(this.state.action_id);
        }
        await this.props.onConfirm(values);
        this.props.close();
    }
}

/** A ribbon across the corner of the form, shown under a condition. */
export class RibbonDialog extends Component {
    static template = "om_pen.RibbonDialog";
    static components = { Dialog };
    props = useProps();

    setup() {
        this.state = proxy({ string: _t("Archived"), bg_color: "text-bg-danger", invisible: "" });
        this.colors = [
            ["text-bg-danger", _t("Red")],
            ["text-bg-success", _t("Green")],
            ["text-bg-warning", _t("Yellow")],
            ["text-bg-info", _t("Blue")],
            ["text-bg-primary", _t("Purple")],
        ];
    }

    async confirm() {
        await this.props.onConfirm({ ...this.state });
        this.props.close();
    }
}

/** Published versions of the view: compare one with the previous, restore it. */
export class VersionsDialog extends Component {
    static template = "om_pen.VersionsDialog";
    static components = { Dialog };
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ versions: [], diff: null, open: null });
        onWillStart(async () => {
            this.state.versions = await this.orm.call("om.pen.studio", "studio_versions", [
                this.props.customizationId,
            ]);
        });
    }

    async showDiff(version) {
        this.state.open = version.id;
        this.state.diff = await this.orm.call("om.pen.studio", "studio_version_diff", [version.id]);
    }

    lineClass(line) {
        if (line.startsWith("+")) {
            return "o_pen_diff_add";
        }
        if (line.startsWith("-")) {
            return "o_pen_diff_del";
        }
        return "";
    }

    async restore(version) {
        await this.props.onRestore(version.id);
        this.props.close();
    }
}
