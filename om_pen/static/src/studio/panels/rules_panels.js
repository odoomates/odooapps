import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { DomainSelectorDialog } from "@web/core/domain_selector_dialog/domain_selector_dialog";
import { studioSections } from "../studio_action";

/** Pick a condition on the records of `model` with Odoo's domain editor. */
function editDomain(dialog, model, domain, title, onConfirm) {
    dialog.add(DomainSelectorDialog, {
        resModel: model,
        domain: domain || "[]",
        isDebugMode: true,
        title,
        onConfirm,
    });
}

// ----------------------------------------------------------------------
// Approvals
// ----------------------------------------------------------------------

export class ApprovalsPanel extends Component {
    static template = "om_pen.ApprovalsPanel";
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.state = proxy({ rules: [], buttons: [], groups: [], users: [], form: null });
        onWillStart(async () => {
            const model = this.model;
            [this.state.rules, this.state.buttons, this.state.groups, this.state.users] = await Promise.all([
                this.orm.call("om.pen.studio", "studio_approval_rules", [model]),
                this.orm.call("om.pen.studio", "studio_approval_buttons", [model]),
                this.orm.call("om.pen.studio", "studio_groups", []),
                this.orm.call("om.pen.studio", "studio_users", []),
            ]);
        });
    }

    get model() {
        return this.props.store.info.model;
    }

    newRule() {
        this.state.form = { id: false, button: "", approver: "group", group_id: "", user_id: "", domain: "[]", name: "" };
    }

    editRule(rule) {
        this.state.form = {
            id: rule.id,
            button: `${rule.button_type}:${rule.button_name}`,
            approver: rule.user_id ? "user" : "group",
            group_id: rule.group_id || "",
            user_id: rule.user_id || "",
            domain: rule.domain,
            name: rule.name,
        };
    }

    pickDomain() {
        editDomain(this.dialog, this.model, this.state.form.domain, _t("Only for the records where"), (domain) => {
            this.state.form.domain = domain;
        });
    }

    async save() {
        const form = this.state.form;
        const [type, ...rest] = form.button.split(":");
        const name = rest.join(":");
        const button = this.state.buttons.find((b) => b.type === type && b.name === name);
        this.state.rules = await this.orm.call("om.pen.studio", "studio_approval_save", [
            this.model,
            {
                id: form.id,
                name: form.name,
                button_name: name,
                button_type: type,
                button_string: button?.string || name,
                group_id: form.approver === "group" ? Number(form.group_id) || false : false,
                user_id: form.approver === "user" ? Number(form.user_id) || false : false,
                domain: form.domain,
            },
        ]);
        this.state.form = null;
    }

    async toggle(rule) {
        this.state.rules = await this.orm.call("om.pen.studio", "studio_approval_toggle", [rule.id, !rule.active]);
    }

    remove(rule) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete the approval rule"),
            body: _t("Delete %s? The button runs without it from now on.", rule.name),
            confirmLabel: _t("Delete"),
            confirmClass: "btn-danger",
            confirm: async () => {
                this.state.rules = await this.orm.call("om.pen.studio", "studio_approval_delete", [rule.id]);
            },
            cancel: () => {},
        });
    }
}

// ----------------------------------------------------------------------
// Automations
// ----------------------------------------------------------------------

export class AutomationsPanel extends Component {
    static template = "om_pen.AutomationsPanel";
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({ data: null, form: null, records: [], testId: "", users: [], installing: false });
        onWillStart(() => this.load());
    }

    get model() {
        return this.props.store.info.model;
    }

    get fields() {
        return Object.values(this.props.store.view?.all_fields || {}).sort((a, b) => a.string.localeCompare(b.string));
    }

    fieldsOf(types) {
        return this.fields.filter((f) => !types || types.includes(f.type));
    }

    async load() {
        this.state.data = await this.orm.call("om.pen.studio", "studio_automations", [this.model]);
        if (this.state.data.installed) {
            this.state.records = await this.orm.call("om.pen.studio", "studio_report_records", [this.model]);
            this.state.users = await this.orm.call("om.pen.studio", "studio_users", []);
        }
    }

    async install() {
        this.state.installing = true;
        await this.orm.call("om.pen.studio", "studio_install_automation", []);
        // the app adds models and screens: the page has to load again
        window.location.reload();
    }

    newRule() {
        this.state.form = {
            name: "",
            trigger: "on_create",
            field: "",
            date_field: "",
            delay: 1,
            delay_type: "day",
            domain: "",
            action: "activity",
            field_to_set: "",
            value: "",
            summary: "",
            days: 0,
            user_id: "",
            template_id: "",
            note: "",
        };
    }

    pickDomain() {
        editDomain(this.dialog, this.model, this.state.form.domain, _t("Only for the records where"), (domain) => {
            this.state.form.domain = domain;
        });
    }

    async create() {
        await this.orm.call("om.pen.studio", "studio_automation_create", [this.model, { ...this.state.form }]);
        this.state.form = null;
        await this.load();
    }

    async update(rule, values) {
        await this.orm.call("om.pen.studio", "studio_automation_update", [rule.id, values]);
        await this.load();
    }

    remove(rule) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete the automation"),
            body: _t("Delete %s?", rule.name),
            confirmLabel: _t("Delete"),
            confirmClass: "btn-danger",
            confirm: () => this.update(rule, { delete: true }),
            cancel: () => {},
        });
    }

    async test(rule) {
        if (!this.state.testId) {
            this.notification.add(_t("Pick a record to test on first."), { type: "warning" });
            return;
        }
        const result = await this.orm.call("om.pen.studio", "studio_automation_test", [rule.id, Number(this.state.testId)]);
        this.notification.add(_t("%(count)s action(s) ran on %(record)s.", { count: result.done, record: result.record }), {
            type: "success",
        });
    }

    openFull(rule) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "base.automation",
            res_id: rule.id,
            views: [[false, "form"]],
            target: "new",
        });
    }
}

// ----------------------------------------------------------------------
// Access rights
// ----------------------------------------------------------------------

const OPERATIONS = [
    ["read", _t("Read")],
    ["write", _t("Edit")],
    ["create", _t("Create")],
    ["unlink", _t("Delete")],
];

export class AccessPanel extends Component {
    static template = "om_pen.AccessPanel";
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.OPERATIONS = OPERATIONS;
        this.state = proxy({ accesses: [], groups: [], users: [], form: null, checkUser: "", check: null, newGroup: "" });
        onWillStart(async () => {
            [this.state.accesses, this.state.groups, this.state.users] = await Promise.all([
                this.orm.call("om.pen.studio", "studio_access", [this.model]),
                this.orm.call("om.pen.studio", "studio_groups", []),
                this.orm.call("om.pen.studio", "studio_users", []),
            ]);
        });
    }

    get model() {
        return this.props.store.info.model;
    }

    get permissions() {
        return this.state.accesses.filter((a) => a.kind === "permission");
    }

    get restrictions() {
        return this.state.accesses.filter((a) => a.kind === "restriction");
    }

    newAccess(kind) {
        this.state.form = {
            kind,
            name: "",
            group_id: "",
            operations: { read: true, write: kind === "permission", create: kind === "permission", unlink: false },
            domain: "",
        };
    }

    pickDomain() {
        editDomain(this.dialog, this.model, this.state.form.domain, _t("For the records where"), (domain) => {
            this.state.form.domain = domain === "[]" ? "" : domain;
        });
    }

    async save() {
        const form = this.state.form;
        this.state.accesses = await this.orm.call("om.pen.studio", "studio_access_save", [
            this.model,
            {
                name: form.name,
                group_id: form.kind === "permission" ? Number(form.group_id) || false : false,
                operations: { ...form.operations },
                domain: form.domain,
            },
        ]);
        this.state.form = null;
    }

    async toggle(access) {
        this.state.accesses = await this.orm.call("om.pen.studio", "studio_access_toggle", [access.id, !access.active]);
    }

    async remove(access) {
        this.state.accesses = await this.orm.call("om.pen.studio", "studio_access_delete", [access.id]);
    }

    async createGroup() {
        const group = await this.orm.call("om.pen.studio", "studio_create_group", [this.state.newGroup]);
        this.state.groups.push(group);
        this.state.newGroup = "";
        if (this.state.form) {
            this.state.form.group_id = group.id;
        }
    }

    async runCheck() {
        if (this.state.checkUser) {
            this.state.check = await this.orm.call("om.pen.studio", "studio_access_check", [
                this.model,
                Number(this.state.checkUser),
            ]);
        }
    }
}

studioSections.add("approvals", { label: _t("Approvals"), Component: ApprovalsPanel }, { sequence: 40 });
studioSections.add("automations", { label: _t("Automations"), Component: AutomationsPanel }, { sequence: 50 });
studioSections.add("access", { label: _t("Access"), Component: AccessPanel }, { sequence: 60 });
