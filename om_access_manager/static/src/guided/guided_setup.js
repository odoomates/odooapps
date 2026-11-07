import { Component, onWillDestroy, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { HelpDialog } from "../help/help_dialog";
import { MenuPanel } from "../menu_tree/menu_panel";
import { FIELD_CYCLE, FieldsPreview } from "./fields_preview";
import { RecordChecklist } from "./record_checklist";

const MODEL = "om.access.profile";
const BUTTON_MODES = [
    ["visible", _t("Visible"), _t("They see the button and can use it."), "visibility", "btn-success"],
    ["hide", _t("Hidden"), _t("Not on the screen, but they could still run it another way."), "visibility_off", "btn-warning"],
    ["hide_block", _t("Blocked"), _t("Not on the screen, and refused however they try it."), "block", "btn-danger"],
];
// the record choices by date of creation: in one list, not as buttons
const DATE_CHOICES = ["today", "week", "month", "year"];
// the fields "Only some" offers as buttons; the others are in a list
const QUICK_FIELDS = 4;
// the pages of the step of an app, in their order
const APP_PAGES = [
    ["menus", _t("Menus")],
    ["records", _t("Records")],
    ["reports", _t("Reports")],
    ["buttons", _t("Buttons")],
    ["fields", _t("Fields")],
];

/**
 * In the rule form opened by My own filter: the New Rule button of its record filter shown
 * where to start, until it is clicked. The form renders after the action: looked for a moment.
 */
function highlightNewRule(tries = 20) {
    const dialogs = document.querySelectorAll(".modal");
    const form = dialogs[dialogs.length - 1];
    const field = form?.querySelector(".o_field_widget[name='domain']");
    const button = [...(field?.querySelectorAll(".o_tree_editor_row > button.btn-link") || [])]
        .find((element) => element.closest(".o_field_widget") === field);
    if (!button) {
        if (tries > 0) {
            setTimeout(() => highlightNewRule(tries - 1), 100);
        }
        return;
    }
    button.classList.add("o_om_highlight");
    button.scrollIntoView({ block: "center", behavior: "smooth" });
    button.addEventListener("click", () => button.classList.remove("o_om_highlight"), { once: true });
}

/**
 * Setup Wizard: a profile set up one question at a time. Who, which apps, then a
 * step for each app (its level, which records, which journals or warehouses),
 * the switches that apply everywhere, and a review. Each answer is saved at once,
 * as on the Configure screen; a new profile stays archived until Finish.
 */
export class GuidedSetupDialog extends Component {
    static template = "om_access_manager.GuidedSetupDialog";
    static components = { Dialog, FieldsPreview, MenuPanel, MultiRecordSelector, RecordChecklist };
    props = useProps({
        close: t.function(),
        profileId: t.number().optional(0),
    });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.buttonModes = BUTTON_MODES;
        this.labels = { print: _t("Print"), actions: _t("Actions"), goTo: _t("Go to this step"),
            block: _t("Block it too: refused even when run another way"),
            tabHide: _t("Shown: click to hide this tab"), tabShow: _t("Hidden: click to show this tab"), unblock: _t("Blocked: click to only hide it") };
        this.printGroups = [["print", _t("Print menu")], ["action", _t("Action menu")]];
        this.state = proxy({
            step: "who",
            profileId: this.props.profileId || 0,
            isNew: !this.props.profileId,
            name: "",
            userIds: [],
            apps: [],
            shownIds: [],
            switches: [],
            app: null,
            appStep: null,
            appPage: "menus",
            // the menus folded on the Menus page
            collapsed: {},
            // the search of the Reports and Buttons pages
            filter: "",
            // apps ticked by hand: a new profile starts with none
            appsPicked: false,
            // the Records page: the data and lists picked to limit, the picker open
            openIds: [],
            openKinds: [],
            // the data whose filter was written with My own filter
            ownFilter: {},
            // the Fields page: the data shown, the search
            fieldsMenu: 0,
            fieldSearch: "",
            // the Fields page: what conditions hide shown too
            fieldShowAll: false,
            picker: false,
            pickerSearch: "",
            // the apps answered: an existing profile has them, a new one once through Apps
            appsSaved: Boolean(this.props.profileId),
            // the apps the name of the profile points to
            suggestedIds: [],
            // "Only some" picked, before any record is
            someOpen: {},
            // the full panel of a data, opened by More settings
            more: {},
            summary: null,
            busy: false,
            search: "",
        });
        onWillStart(() => this.state.profileId && this.load());
        // closed in any way but Finish: a new profile goes, the screen below shows the changes
        onWillDestroy(() => {
            if (this.finished) {
                return;
            }
            const orm = this.env.services.orm;
            const draft = this.state.isNew && this.state.profileId;
            Promise.resolve(draft && orm.call(MODEL, "om_guided_discard", [[draft]])).finally(() =>
                this.env.services.action.doAction({ type: "ir.actions.client", tag: "soft_reload" })
            );
        });
    }

    async load() {
        const data = await this.orm.call(MODEL, "om_guided_state", [[this.state.profileId]]);
        Object.assign(this.state, {
            name: data.name,
            userIds: data.user_ids,
            apps: data.apps,
            shownIds: data.apps.filter((app) => app.shown).map((app) => app.id),
            switches: data.switches,
            suggestedIds: data.suggested_ids || [],
            isNew: this.state.isNew || data.is_draft,
        });
    }

    // the steps: who, apps, one for each app shown, everywhere, review

    get steps() {
        const shown = new Set(this.state.shownIds);
        return [
            { key: "who", label: _t("Who") },
            { key: "apps", label: _t("Apps") },
            ...this.state.apps.filter((app) => shown.has(app.id))
                .map((app) => ({ key: `app:${app.id}`, label: app.name, app })),
            { key: "everywhere", label: _t("Everywhere") },
            { key: "review", label: _t("Review") },
        ];
    }

    get stepIndex() {
        return this.steps.findIndex((step) => step.key === this.state.step);
    }

    get title() {
        return this.state.isNew ? _t("Setup Wizard: New Profile") : _t("Setup Wizard: %s", this.state.name);
    }

    stepClass(step, index) {
        const current = this.stepIndex;
        return index < current ? "o_om_guided_done" : index === current ? "o_om_guided_current" : "o_om_guided_ahead";
    }

    async run(callback) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            return await callback();
        } finally {
            this.state.busy = false;
        }
    }

    // the pages of the step of an app: those with something to set

    get appPages() {
        const step = this.state.appStep;
        if (!step) {
            return [];
        }
        const pages = APP_PAGES.filter(([key]) => {
            if (key === "menus") {
                return step.menus.length;
            }
            if (key === "records") {
                return step.data_choices.length || step.allowed.length || step.has_children;
            }
            if (key === "reports") {
                return step.data.some((entry) => entry.print.length);
            }
            if (key === "fields") {
                return step.data.some((entry) => entry.has_form || entry.fields.length);
            }
            return step.data.some((entry) => entry.buttons.length);
        });
        return pages.length ? pages : [APP_PAGES[1]];
    }

    get appPageIndex() {
        return this.appPages.findIndex(([key]) => key === this.state.appPage);
    }

    get onAppStep() {
        return this.state.step.startsWith("app:");
    }

    openAppPage(key) {
        this.state.more = {};
        this.state.filter = "";
        this.state.appPage = key;
    }

    next() {
        if (this.onAppStep && this.appPageIndex < this.appPages.length - 1) {
            return this.openAppPage(this.appPages[this.appPageIndex + 1][0]);
        }
        return this.run(async () => {
            if (!(await this.saveStep())) {
                return;
            }
            await this.go(this.steps[this.stepIndex + 1]);
        });
    }

    back() {
        if (this.onAppStep && this.appPageIndex > 0) {
            return this.openAppPage(this.appPages[this.appPageIndex - 1][0]);
        }
        return this.run(() => this.go(this.steps[this.stepIndex - 1]));
    }

    /** Any step, back or ahead: the current one is saved first, as with Next. The steps
     * after Apps come from the apps ticked: a new profile goes through Apps once first. */
    jump(index) {
        if (index === this.stepIndex) {
            return;
        }
        const target = this.steps[index];
        if (index < this.stepIndex) {
            return this.state.profileId && this.run(() => this.go(target));
        }
        return this.run(async () => {
            if (!(await this.saveStep())) {
                return;
            }
            // saving Who may change the steps (the apps of the profile): found again by key
            const steps = this.steps;
            let dest = steps.find((step) => step.key === target.key) || steps[Math.min(index, steps.length - 1)];
            const appsIndex = steps.findIndex((step) => step.key === "apps");
            if (!this.state.appsSaved && steps.indexOf(dest) > appsIndex) {
                this.notification.add(_t("First tick the apps: the next steps come from them."), { type: "info" });
                dest = steps[appsIndex];
            }
            await this.go(dest);
        });
    }

    async go(step) {
        if (!step) {
            return;
        }
        this.state.more = {};
        this.state.someOpen = {};
        if (step.app) {
            this.state.openIds = [];
            this.state.openKinds = [];
            this.state.fieldsMenu = 0;
            this.state.fieldSearch = "";
            this.state.picker = false;
            this.state.appStep = await this.appCall("om_guided_app", [[this.state.profileId], step.app.id]);
            this.state.app = step.app;
            this.state.appPage = this.appPages[0][0];
            this.state.collapsed = {};
        }
        if (step.key === "review") {
            this.state.summary = await this.orm.call(MODEL, "om_guided_summary", [[this.state.profileId]]);
        }
        this.state.step = step.key;
    }

    /** What Next saves: the name and users, the apps; the other steps save each answer at once. */
    async saveStep() {
        if (this.state.step === "who") {
            if (!this.state.name.trim()) {
                this.notification.add(_t("Give the profile a name."), { type: "warning" });
                return false;
            }
            if (!this.state.profileId) {
                this.state.profileId = await this.orm.call(MODEL, "om_guided_new", [this.state.name, this.state.userIds]);
            } else {
                await this.orm.call(MODEL, "om_guided_set_who", [[this.state.profileId], this.state.name, this.state.userIds]);
            }
            const shown = this.state.shownIds;
            await this.load();
            if (this.state.isNew) {
                // a new profile: the apps ticked here, or to start with those its name points to
                // ("Project User": Project), which the user adds to or unticks
                this.state.shownIds = this.state.appsPicked ? shown : this.state.suggestedIds;
            }
        } else if (this.state.step === "apps") {
            if (!this.state.shownIds.length) {
                this.notification.add(_t("Tick at least one app."), { type: "warning" });
                return false;
            }
            await this.orm.call(MODEL, "om_guided_set_apps", [[this.state.profileId], this.state.shownIds]);
            this.state.appsSaved = true;
        }
        return true;
    }

    // step 1: who

    setUsers(ids) {
        this.state.userIds = ids;
    }

    // step 2: apps

    get filteredApps() {
        const search = this.state.search.trim().toLowerCase();
        return search ? this.state.apps.filter((app) => app.name.toLowerCase().includes(search)) : this.state.apps;
    }

    get suggestedNames() {
        const shown = new Set(this.state.shownIds);
        return this.state.apps.filter((app) => this.state.suggestedIds.includes(app.id) && shown.has(app.id))
            .map((app) => app.name);
    }

    isShown(app) {
        return this.state.shownIds.includes(app.id);
    }

    toggleApp(app) {
        this.state.appsPicked = true;
        this.state.shownIds = this.isShown(app)
            ? this.state.shownIds.filter((id) => id !== app.id)
            : [...this.state.shownIds, app.id];
    }

    setAllApps(shown) {
        this.state.appsPicked = true;
        this.state.shownIds = shown ? this.state.apps.map((app) => app.id) : [];
    }

    // a step of an app

    applyApp(menuId, change) {
        return this.run(async () => {
            this.state.appStep = await this.appCall("om_guided_app_set", [[this.state.profileId], this.state.app.id, menuId, change]
            );
        });
    }

    // the Menus page: the menus of the app as in its top bar, a card for each, folding

    get menuTree() {
        const roots = [];
        const stack = [];
        for (const menu of this.state.appStep?.menus || []) {
            const node = { menu, children: [] };
            stack.length = menu.depth;
            if (menu.depth === 0) {
                roots.push(node);
            } else if (stack[menu.depth - 1]) {
                stack[menu.depth - 1].children.push(node);
            }
            stack[menu.depth] = node;
        }
        return roots;
    }

    isCollapsed(node) {
        // the cards open, the menus deeper down folded, until clicked
        const value = this.state.collapsed[node.menu.id];
        return value === undefined ? node.menu.depth > 0 : value;
    }

    toggleCollapse(node) {
        this.state.collapsed[node.menu.id] = !this.isCollapsed(node);
    }

    setAllCollapsed(value) {
        const collapsed = {};
        for (const menu of this.state.appStep?.menus || []) {
            collapsed[menu.id] = value;
        }
        this.state.collapsed = collapsed;
    }

    /** The menus under a card, in order, those under a folded menu left out. */
    cardItems(node) {
        const items = [];
        const walk = (parent) => {
            for (const child of parent.children) {
                items.push(child);
                if (child.children.length && !this.isCollapsed(child)) {
                    walk(child);
                }
            }
        };
        walk(node);
        return items;
    }

    countBelow(node) {
        return node.children.reduce((count, child) => count + 1 + this.countBelow(child), 0);
    }

    menuDescendants(menuId) {
        const menus = this.state.appStep?.menus || [];
        const start = menus.findIndex((menu) => menu.id === menuId);
        const result = [];
        // in tree order: those after it, deeper than it, until one at its depth or above
        for (let index = start + 1; start >= 0 && index < menus.length && menus[index].depth > menus[start].depth; index++) {
            result.push(menus[index]);
        }
        return result;
    }

    setReadOnly(value) {
        return this.run(async () => {
            this.state.appStep = await this.appCall("om_guided_set_read_only", [[this.state.profileId], this.state.app.id, value]
            );
        });
    }

    // menus, reports and buttons of an app

    // each shows the answer at once, before the server has it: the box does not flick back

    setMenu(menu, shown) {
        menu.hidden = !shown;
        // the menus under it follow it at once, as the server makes them
        const below = this.menuDescendants(menu.id);
        below.forEach((child) => {
            child.hidden = false;
            child.hidden_above = !shown;
        });
        return this.applyApp(menu.id, { kind: "hide_menu", hidden: !shown });
    }

    setPrint(entry, item, allowed) {
        item.hidden = !allowed;
        return this.applyApp(entry.menu_id, { kind: "print", type: item.type, id: item.id, hidden: !allowed });
    }

    setButton(entry, button, mode) {
        button.mode = mode;
        return this.applyApp(entry.menu_id, {
            kind: "button", button_type: button.button_type, button_name: button.button_name,
            mode, label: button.label, condition: button.condition,
        });
    }

    // the Reports and Buttons pages: a search, and all at once

    get filterPlaceholder() {
        return this.state.appPage === "reports" ? _t("Search a report or action...") : _t("Search a button...");
    }

    matches(label) {
        const filter = this.state.filter.trim().toLowerCase();
        return !filter || (label || "").toLowerCase().includes(filter);
    }

    printsOf(entry, type) {
        return entry.print.filter((item) => (type === "print") === (item.type === "ir.actions.report")
            && this.matches(item.label));
    }

    /** Blocked without hiding is shown as Blocked: the pop-up offers hide and block together. */
    buttonMode(button) {
        return button.mode === "block" ? "hide_block" : button.mode;
    }

    // the Fields page: the form of a data, its fields set by clicking them

    get fieldsEntries() {
        return (this.state.appStep?.data || []).filter((entry) => entry.has_form || entry.fields.length);
    }

    get fieldsEntry() {
        const entries = this.fieldsEntries;
        return entries.find((entry) => entry.menu_id === this.state.fieldsMenu) || entries[0];
    }

    openFieldsData(entry) {
        this.state.fieldsMenu = entry.menu_id;
        this.state.fieldSearch = "";
    }

    /** A field clicked: read only, hidden, as before. One with a condition or required is
     * set in More settings, where that is kept. */
    cycleField(entry, field) {
        if (field.condition || field.mode === "required") {
            this.notification.add(_t("%s has more settings (a condition or required): change it in More settings.", field.label),
                { type: "info" });
            if (!this.state.more[entry.menu_id]) {
                this.toggleMore(entry);
            }
            return;
        }
        const mode = FIELD_CYCLE[field.mode] || "readonly";
        field.mode = mode;
        return this.applyApp(entry.menu_id, { kind: "field", field: field.name, mode });
    }

    changedFields(entry) {
        return entry.fields.filter((field) => field.mode !== "keep" || field.condition);
    }

    fieldTag(field) {
        if (field.condition) {
            return _t("%s, when...", this.fieldModeLabel(field.mode));
        }
        return this.fieldModeLabel(field.mode);
    }

    fieldModeLabel(mode) {
        return { readonly: _t("Read only"), hide: _t("Hidden"), required: _t("Required"), keep: _t("Normal") }[mode] || mode;
    }

    resetFields(entry) {
        const changes = entry.fields.filter((field) => ["readonly", "hide"].includes(field.mode) && !field.condition)
            .map((field) => ({ kind: "field", field: field.name, mode: "keep" }));
        return this.applyMany(entry.menu_id, changes);
    }

    toggleTab(entry, tab) {
        tab.hidden = !tab.hidden;
        return this.applyApp(entry.menu_id, {
            kind: "element", element_type: "page", element_name: tab.element_name, hidden: tab.hidden,
            label: tab.label,
        });
    }

    /** A click on a button: hidden, or shown again. */
    toggleButton(entry, button) {
        return this.setButton(entry, button, this.buttonMode(button) === "visible" ? "hide" : "visible");
    }

    /** The lock of a hidden button: blocked as well, or only hidden. */
    toggleBlock(entry, button) {
        return this.setButton(entry, button, this.buttonMode(button) === "hide_block" ? "hide" : "hide_block");
    }

    buttonTitle(button) {
        const mode = this.buttonMode(button);
        const state = mode === "visible" ? _t("Shown: click to hide it")
            : mode === "hide" ? _t("Hidden: click to show it") : _t("Blocked: click to show it");
        return `${button.label} (${button.button_name})\n${state}`;
    }

    buttonsAt(buttons, place) {
        return buttons.filter((button) => (button.place || "other") === place);
    }

    buttonsOf(entry) {
        return entry.buttons.filter((button) => this.matches(button.label));
    }

    applyMany(menuId, changes) {
        if (!changes.length) {
            return;
        }
        return this.run(async () => {
            this.state.appStep = await this.appCall("om_guided_app_set_many", [[this.state.profileId], this.state.app.id, menuId, changes]
            );
        });
    }

    setAllPrints(entry, items, allowed) {
        const changes = items.filter((item) => item.hidden === allowed)
            .map((item) => ({ kind: "print", type: item.type, id: item.id, hidden: !allowed }));
        items.forEach((item) => (item.hidden = !allowed));
        return this.applyMany(entry.menu_id, changes);
    }

    setAllButtons(entry, buttons, mode) {
        const changes = buttons.filter((button) => button.mode !== mode).map((button) => ({
            kind: "button", button_type: button.button_type, button_name: button.button_name,
            mode, label: button.label, condition: button.condition,
        }));
        buttons.forEach((button) => (button.mode = mode));
        return this.applyMany(entry.menu_id, changes);
    }

    // the Records page: they see everything, until a data or a list is picked and limited

    /** A call returning the step of the app, with the data picked on the Records page. */
    appCall(method, args) {
        return this.orm.call(MODEL, method, args, { context: { om_guided_open: this.state.openIds } });
    }

    /** The lists of an app (journals, teams, warehouses) limited, or picked on the page. */
    get allowedCards() {
        const step = this.state.appStep;
        return (step?.allowed || []).filter((kind) => kind.records.length || kind.per_user
            || this.state.openKinds.includes(kind.kind));
    }

    get hasLimits() {
        const step = this.state.appStep;
        return Boolean(step && (step.records.some((entry) => entry.records !== "all") || this.allowedCards
            .some((kind) => kind.records.length || kind.per_user)));
    }

    /** The picker: the data of the app under the menus of its top bar, then its lists. */
    get pickerGroups() {
        const step = this.state.appStep;
        if (!step) {
            return [];
        }
        const search = this.state.pickerSearch.trim().toLowerCase();
        const match = (...texts) => !search || texts.some((text) => (text || "").toLowerCase().includes(search));
        const shown = new Set(step.records.map((entry) => entry.menu_id));
        const groups = [];
        for (const choice of step.data_choices) {
            if (!match(choice.menu, choice.label, choice.group)) {
                continue;
            }
            const name = choice.config ? _t("Configuration") : choice.group;
            let group = groups.find((item) => item.name === name);
            if (!group) {
                group = { name, items: [] };
                groups.push(group);
            }
            group.items.push({ key: `data:${choice.menu_id}`, name: choice.menu, detail: choice.label,
                common: choice.common, picked: shown.has(choice.menu_id), choice });
        }
        // the configuration last
        groups.sort((a, b) => (a.name === _t("Configuration")) - (b.name === _t("Configuration")));
        const lists = (step.allowed || []).filter((kind) => match(kind.label)).map((kind) => ({
            key: `kind:${kind.kind}`, name: kind.label, detail: _t("which ones they use"), common: true,
            picked: this.allowedCards.includes(kind), kind,
        }));
        if (lists.length) {
            groups.unshift({ name: _t("Lists they work with"), items: lists });
        }
        return groups;
    }

    togglePicker() {
        this.state.picker = !this.state.picker;
        this.state.pickerSearch = "";
    }

    pick(item) {
        this.state.picker = false;
        if (item.picked) {
            return;
        }
        if (item.kind) {
            this.state.openKinds = [...this.state.openKinds, item.kind.kind];
            return;
        }
        this.state.openIds = [...this.state.openIds, item.choice.menu_id];
        return this.run(async () => {
            this.state.appStep = await this.appCall("om_guided_app", [[this.state.profileId], this.state.app.id]);
        });
    }

    /** A card removed: its data seen in full again. */
    removeCard(entry) {
        this.state.openIds = this.state.openIds.filter((id) => id !== entry.menu_id);
        delete this.state.someOpen[entry.menu_id];
        delete this.state.more[entry.menu_id];
        if (entry.records === "all") {
            return this.run(async () => {
                this.state.appStep = await this.appCall("om_guided_app", [[this.state.profileId], this.state.app.id]);
            });
        }
        return this.applyApp(entry.menu_id, { kind: "data_rights", records: "all" });
    }

    async removeKind(kind) {
        this.state.openKinds = this.state.openKinds.filter((name) => name !== kind.kind);
        if (kind.per_user) {
            await this.setAllowedPerUser(kind, false);
        }
        if (kind.records.length) {
            await this.setAllowed(kind, []);
        }
    }

    /** My own filter: the rule form of this data, with Odoo's filter editor; the step again after. */
    openOwnFilter(entry) {
        return this.run(async () => {
            const panel = await this.orm.call(MODEL, "om_menu_panel_set",
                [[this.state.profileId], entry.menu_id, { kind: "data_line" }]);
            if (!panel.line_id) {
                return;
            }
            const action = await this.orm.call("om.access.profile.model", "action_open_rule", [[panel.line_id]]);
            // the form of a filter of one's own: without the ready-made choices of the card
            action.context = { ...(action.context || {}), om_own_filter: true };
            this.state.ownFilter[entry.menu_id] = true;
            this.state.someOpen[entry.menu_id] = false;
            await this.action.doAction(action, {
                onClose: () => this.run(async () => {
                    this.state.appStep = await this.appCall("om_guided_app", [[this.state.profileId], this.state.app.id]);
                }),
            });
            highlightNewRule();
        });
    }

    choiceLabel(entry) {
        const choice = this.recordsChoice(entry);
        if (choice === "some") {
            return _t("Only some");
        }
        if (choice === "custom" || choice === "filter") {
            return _t("A filter of its own");
        }
        return (entry.choices.find((option) => option[0] === choice) || [null, _t("All")])[1];
    }

    mainChoices(entry) {
        return entry.choices.filter((choice) => !DATE_CHOICES.includes(choice[0]));
    }

    /** "this month" of "Created this month": the radio says Created. */
    dateLabel(option) {
        const labels = { today: _t("today"), week: _t("this week"), month: _t("this month"), year: _t("this year") };
        return labels[option[0]] || option[1];
    }

    dateChoices(entry) {
        return entry.choices.filter((choice) => DATE_CHOICES.includes(choice[0]));
    }

    quickFields(entry) {
        return entry.filter_fields.slice(0, QUICK_FIELDS);
    }

    otherFields(entry) {
        return entry.filter_fields.slice(QUICK_FIELDS);
    }

    countText(entry) {
        const count = entry.count;
        if (!count) {
            return "";
        }
        if (count.kept === false) {
            return _t("Depends on each user: %s in all.", count.total);
        }
        return _t("They will see %(kept)s of %(total)s.", { kept: count.kept, total: count.total });
    }

    recordsChoice(entry) {
        // written through My own filter: shown so, even when it reads as Only some
        if (this.state.ownFilter[entry.menu_id] && entry.records !== "all") {
            return "custom";
        }
        if (this.state.someOpen[entry.menu_id] || entry.records === "some") {
            return "some";
        }
        return entry.records;
    }

    setRecords(entry, value) {
        this.state.ownFilter[entry.menu_id] = false;
        if (value === "some") {
            this.state.someOpen[entry.menu_id] = true;
            return;
        }
        this.state.someOpen[entry.menu_id] = false;
        return this.applyApp(entry.menu_id, { kind: "data_rights", records: value });
    }

    /** The single row of "Only some": a field, its records, and the user for a user field. */
    someRow(entry) {
        const row = entry.simple_filter[0];
        const field = entry.filter_fields.find((field) => field.name === (row ? row.field : this.state.someOpen[`${entry.menu_id}:field`]))
            || entry.filter_fields[0];
        return {
            field,
            ids: row && field && row.field === field.name ? row.records.map((record) => record.id) : [],
            me: Boolean(row && row.me),
        };
    }

    hasMoreRows(entry) {
        return entry.simple_filter.length > 1;
    }

    setSomeField(entry, name) {
        this.state.someOpen[entry.menu_id] = true;
        this.state.someOpen[`${entry.menu_id}:field`] = name;
        if (entry.simple_filter.length) {
            // another field: the records of the old one do not apply to it
            return this.applyApp(entry.menu_id, { kind: "data_rights", records: "all" });
        }
    }

    setSome(entry, ids, me) {
        const row = this.someRow(entry);
        if (!row.field) {
            return;
        }
        if (!ids.length && !me) {
            this.state.someOpen[entry.menu_id] = true;
            return this.applyApp(entry.menu_id, { kind: "data_rights", records: "all" });
        }
        return this.applyApp(entry.menu_id, { kind: "data_filter", rows: [{ field: row.field.name, ids, me }] });
    }

    setLinked(entry, link, on) {
        return this.applyApp(entry.menu_id, { kind: "data_linked", model: link.model, field: link.field, remove: !on });
    }

    setAllowed(kind, ids) {
        return this.run(async () => {
            const current = kind.records;
            const added = ids.filter((id) => !current.some((record) => record.id === id));
            const removed = current.filter((record) => !ids.includes(record.id));
            for (const id of added) {
                await this.orm.call(MODEL, "om_menu_panel_set", [[this.state.profileId], this.state.app.id,
                    { kind: "allowed", allowed_kind: kind.kind, add: id }]);
            }
            for (const record of removed) {
                await this.orm.call(MODEL, "om_menu_panel_set", [[this.state.profileId], this.state.app.id,
                    { kind: "allowed", allowed_kind: kind.kind, remove: record.line_id }]);
            }
            this.state.appStep = await this.appCall("om_guided_app", [[this.state.profileId], this.state.app.id]);
        });
    }

    setAllowedPerUser(kind, value) {
        return this.applyApp(this.state.app.id, { kind: "allowed", allowed_kind: kind.kind, per_user: value });
    }

    allowedIds(kind) {
        return kind.records.map((record) => record.id);
    }

    // More settings: the full panel of the Configure screen, for one data

    async toggleMore(entry) {
        if (this.state.more[entry.menu_id]) {
            delete this.state.more[entry.menu_id];
            return;
        }
        this.state.more[entry.menu_id] = await this.orm.call(MODEL, "om_menu_panel", [[this.state.profileId], entry.menu_id]);
    }

    morePanelApply(entry) {
        return (change) => this.run(async () => {
            this.state.more[entry.menu_id] = await this.orm.call(
                MODEL, "om_menu_panel_set", [[this.state.profileId], entry.menu_id, change]
            );
            this.state.appStep = await this.appCall("om_guided_app", [[this.state.profileId], this.state.app.id]);
        });
    }

    moreOpenRule(entry) {
        return async () => {
            await this.morePanelApply(entry)({ kind: "data_line" });
            const lineId = this.state.more[entry.menu_id]?.line_id;
            if (lineId) {
                const action = await this.orm.call("om.access.profile.model", "action_open_rule", [[lineId]]);
                await this.action.doAction(action, {
                    onClose: () => this.morePanelApply(entry)({ kind: "data_rights" }),
                });
            }
        };
    }

    // everywhere

    setSwitch(entry, value) {
        return this.run(async () => {
            await this.orm.call(MODEL, "om_guided_set_switch", [[this.state.profileId], entry.name, value]);
            entry.value = value;
        });
    }

    // the end

    /** The users, added or removed on the Review step: saved at once, the summary again. */
    setReviewUsers(ids) {
        this.state.userIds = ids;
        return this.run(async () => {
            await this.orm.call(MODEL, "om_guided_set_who", [[this.state.profileId], this.state.name, ids]);
            this.state.summary = await this.orm.call(MODEL, "om_guided_summary", [[this.state.profileId]]);
        });
    }

    previewAsUser() {
        return this.run(async () => {
            const action = await this.orm.call(MODEL, "action_test_user", [[this.state.profileId]]);
            await this.action.doAction(action);
        });
    }

    finish() {
        return this.run(async () => {
            const action = await this.orm.call(MODEL, "om_guided_finish", [[this.state.profileId]]);
            this.finished = true;
            this.props.close();
            await this.action.doAction(action);
        });
    }

    cancel() {
        this.props.close();
    }

    openHelp() {
        this.dialog.add(HelpDialog, { topic: "guided" });
    }
}

/** The client action of the Setup Wizard buttons: the pop-up over the current screen. */
function guidedSetupAction(env, action) {
    const profileId = action.params?.profile_id || 0;
    env.services.dialog.add(GuidedSetupDialog, { profileId });
}

registry.category("actions").add("om_access_guided_setup", guidedSetupAction);
