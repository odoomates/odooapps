import { Component, proxy, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

// One page per thing people come to do, in the words of the screen they do it on, grouped in tabs.
export const HELP_GROUPS = [
    { key: "start", title: _t("Getting started") },
    { key: "records", title: _t("Records") },
    { key: "screens", title: _t("Screens") },
    { key: "users", title: _t("Users") },
    { key: "know", title: _t("Good to know") },
];

export const HELP_TOPICS = [
    {
        key: "templates", group: "start", gif: true,
        title: _t("Start from a template"),
        intro: _t("Ready-made profiles for common jobs: Salesperson, Warehouse Operator, Cashier, Project Team Member..."),
        steps: [
            _t("Open Access Manager / Access Profiles and click New from Template."),
            _t("Pick the template of the job, then create the profile."),
            _t("Add the users, then adjust what is needed in the menu tree."),
        ],
        tips: [_t("A template only fills a new profile: change it freely afterwards.")],
    },
    {
        key: "guided", group: "start",
        title: _t("Setup Wizard"),
        intro: _t("A profile set up one question at a time, on screens that look like Odoo itself."),
        steps: [
            _t("Click Setup Wizard on the list of profiles for a new one, or on a profile to go through it again."),
            _t("Who: name the profile and add its users. Apps: tick the apps they work in; the apps the name points to are ticked for you (Project User ticks Project)."),
            _t("Menus: the top bar of the app. Click a menu, or its name, to hide it; a main menu takes its submenus with it."),
            _t("Records: they see all records until you limit some. Click Limit records of..., pick the data, then choose Their own records, Their sales team, Only some... or My own filter."),
            _t("Reports: untick entries of the Print and Actions menus. Buttons: click a button to hide it, click its lock to block it as well."),
            _t("Fields: the real form. Click a field once for read only, twice for hidden, a third time for normal again."),
            _t("Everywhere: what they may not do in any app, such as export. Review: check, add or remove users, Preview as User, then Finish."),
        ],
        tips: [
            _t("Click a step at the top to go to it, back or ahead: the current step is saved first."),
            _t("On Fields, Show fields hidden by conditions shows the fields of other states too, to set them as well."),
            _t("My own filter opens Odoo's filter editor; its buttons add a condition on the user, such as Salesperson = current user."),
            _t("A new profile applies only from Finish. On a profile in use, each answer applies at once."),
        ],
    },
    {
        key: "configure", group: "start", gif: true,
        title: _t("Configure a profile"),
        intro: _t("Everything is set from the menus, the way users see Odoo."),
        steps: [
            _t("Open the profile and click Configure: the menu tree takes the whole screen."),
            _t("Untick a menu to hide it. Click a menu (anywhere on its row: Configure >) to set what users may do there."),
            _t("Every change is saved at once. The breadcrumb takes you back to the profile."),
        ],
        tips: [
            _t("The same tree is in the Menus & Apps tab of the profile."),
            _t("Restrict an App, at the top, limits a whole app in a few clicks."),
        ],
    },
    {
        key: "apps", group: "start", gif: true,
        title: _t("Hide an app or a menu"),
        intro: _t("Users do not see what is hidden, nor anything below it."),
        steps: [
            _t("In the menu tree, untick the app or the menu to hide it."),
            _t("Or click an app and choose its level: Full access, No configuration, Read only or No access."),
            _t("Restrict an App does the same in a few clicks, for an app at a time."),
        ],
        tips: [_t("Hiding a menu hides the way in, not the data: to block the data, untick its rights too.")],
    },
    {
        key: "rights", group: "start", gif: true,
        title: _t("Read only, or no deleting"),
        intro: _t("Decide what users may do with the data of a menu."),
        steps: [
            _t("In the menu tree, click the menu."),
            _t("Under Rights, untick Create, Edit or Delete."),
            _t("To allow editing only the drafts, tick Edit drafts only when it is offered."),
        ],
        tips: [
            _t("Rights are on the data: they apply on every menu showing it."),
            _t("A menu with children passes its rights down to them."),
        ],
    },
    {
        key: "records", group: "records", gif: true,
        title: _t("Show only some records"),
        intro: _t("For instance the tasks of two projects, or the sales of a team or a salesperson."),
        steps: [
            _t("In the menu tree, click the menu, say Project / Tasks / All Tasks."),
            _t("Set Records to Only some records."),
            _t("Choose the field, say Project, then add the projects from the Add... list."),
            _t("Add a condition for another field: a record matching any of them is shown."),
        ],
        tips: [
            _t("For a field pointing to users, tick 'or the user themselves': each salesperson sees their own."),
            _t("The filter is on the data, not on the menu: My Tasks shows the same tasks."),
            _t("Advanced... opens the full editor, for anything the rows cannot say; its buttons add Salesperson = current user and the like."),
        ],
    },
    {
        key: "linked", group: "records", gif: true,
        title: _t("Limit the linked data too"),
        intro: _t("Keep some customers only, and their sales orders, invoices and tasks with them."),
        steps: [
            _t("Limit the records first, say Customers whose tag is Retail."),
            _t("Under the rows, click the data to limit the same way, say + Sales Order (Customer)."),
            _t("Click it again to undo."),
        ],
        tips: [_t("Data with a filter of its own shows 'own filter': change that one on its menu, with Advanced....")],
    },
    {
        key: "allowed", group: "records", gif: false,
        title: _t("Only some journals, shops or warehouses"),
        intro: _t("Allowed records also filter what belongs to them: the entries of a journal, the orders of a shop."),
        steps: [
            _t("In the menu tree, click the app: Invoicing, Point of Sale or Inventory."),
            _t("Under Allowed records, add the journals, points of sale or warehouses."),
            _t("Or tick Each user's own and set them on each user's form, in the Access Profiles tab."),
        ],
        tips: [_t("One profile can then serve every cashier, each on their own point of sale.")],
    },
    {
        key: "fields", group: "screens", gif: true,
        title: _t("Hide or lock a field or a button"),
        intro: _t("For instance hide the cost of a product, or the Confirm button of an order."),
        steps: [
            _t("In the menu tree, click the menu that shows the form."),
            _t("Open Fields and set the field to Read-only, Hidden or Required."),
            _t("Open Buttons and set the button to Hidden or Blocked."),
            _t("To apply it only sometimes, type a condition in Only when..., say state == 'sale'."),
        ],
        tips: [
            _t("In the Setup Wizard, the Fields and Buttons pages show the real form: click a field or a button there instead."),
            _t("Hidden takes the button off the screen. Blocked also refuses it if it is called another way."),
            _t("A hidden field is blank for these users in lists, exports and the external API too."),
        ],
    },
    {
        key: "reports", group: "screens", gif: false,
        title: _t("Hide reports and actions"),
        intro: _t("Take reports off the Print menu, and entries off the Action menu."),
        steps: [
            _t("In the menu tree, click the menu."),
            _t("Open Print and untick the reports to hide."),
            _t("Open Action Menu and untick the entries to hide."),
        ],
        tips: [_t("To hide every report at once, use Hide the Print Menu in the Restrictions tab.")],
    },
    {
        key: "switches", group: "screens", gif: false,
        title: _t("Restrictions for everything at once"),
        intro: _t("One tick for the whole of Odoo: read only, no export, no import, chatter hidden..."),
        steps: [
            _t("Open the Restrictions tab of the profile."),
            _t("Tick what applies to these users everywhere, say Block Export."),
        ],
        tips: [_t("The same restrictions exist per menu, at the bottom of its panel, for one kind of data only.")],
    },
    {
        key: "preview", group: "users", gif: true,
        title: _t("Check what a user sees"),
        intro: _t("See Odoo as one of the users of the profile, without their password."),
        steps: [
            _t("Add the user under Users, at the top of the profile."),
            _t("Click Preview as User, pick the user, then Open Preview."),
            _t("Odoo opens as that user, read only. Click Exit preview in the banner at the bottom to come back."),
        ],
        tips: [
            _t("Settings users are left alone, unless Apply to Settings Users is ticked in Options."),
            _t("Why? in the menu explains why a user can or cannot do something."),
        ],
    },
    {
        key: "signin", group: "users", gif: false,
        title: _t("Sign-in hours and networks"),
        intro: _t("Allow signing in only at work, from the office network, from one place at a time."),
        steps: [
            _t("Open the Sign-in tab of the profile."),
            _t("Under Working Hours, add the days and hours, and the timezone."),
            _t("Under Networks and Sessions, list the allowed networks, or tick Single Session."),
        ],
        tips: [_t("Block Login refuses every sign-in of these users and ends their open sessions.")],
    },
    {
        key: "temporary", group: "users", gif: false,
        title: _t("Give access for a while"),
        intro: _t("A user covering for a colleague, for the length of the holiday."),
        steps: [
            _t("Open the Temporary Users tab of the profile."),
            _t("Add the user, with the first and the last day."),
        ],
        tips: [_t("The profile applies from the first day and is taken away after the last one, by itself.")],
    },
    {
        key: "copy", group: "users", gif: false,
        title: _t("Copy a user's access"),
        intro: _t("Give a new colleague the same access as someone in the same job."),
        steps: [
            _t("Open the user under Settings / Users, Access Profiles tab."),
            _t("Click Copy Access to..., pick the other users, then copy."),
        ],
        tips: [_t("Copying gives the same profiles: a later change of a profile reaches all of them.")],
    },
    {
        key: "traps", group: "know", gif: true,
        title: _t("Good to know"),
        intro: _t("What most often surprises people."),
        steps: [
            _t("Profiles add up: a user in two profiles may do what either allows. Set Strictness to Override in Options to always apply a profile."),
            _t("A filter on records also hides the new ones that do not match it."),
            _t("Health Check, in the Action menu of a profile or in the top menu, lists the rules that no longer fit the database, after an update for instance."),
            _t("Every change is kept: the Versions button at the top takes the profile back to an earlier state."),
        ],
        tips: [_t("A field marked 'may be slow on large data' has no database index: ask your developer to add one if lists get slow.")],
    },
];

export class HelpDialog extends Component {
    static template = "om_access_manager.HelpDialog";
    static components = { Dialog };
    props = useProps({
        close: t.function(),
        topic: t.string().optional("records"),
    });

    setup() {
        this.groups = HELP_GROUPS;
        const topic = HELP_TOPICS.find((topic) => topic.key === this.props.topic) || HELP_TOPICS[0];
        this.state = proxy({ group: topic.group, topic: topic.key });
    }

    get topics() {
        return HELP_TOPICS.filter((topic) => topic.group === this.state.group);
    }

    get current() {
        return HELP_TOPICS.find((topic) => topic.key === this.state.topic) || this.topics[0];
    }

    openGroup(key) {
        this.state.group = key;
        this.state.topic = this.topics[0].key;
    }

    gif(topic) {
        return `/om_access_manager/static/src/help/img/${topic.key}.gif`;
    }
}

// the Help button of a form: <widget name="om_access_help" topic="records"/>
export class HelpButton extends Component {
    static template = "om_access_manager.HelpButton";
    props = useProps({
        ...standardWidgetProps,
        record: t.object().optional(),
        topic: t.string().optional(),
    });

    setup() {
        this.dialog = useService("dialog");
    }

    open() {
        this.dialog.add(HelpDialog, { topic: this.props.topic || "records" });
    }
}

registry.category("view_widgets").add("om_access_help", {
    component: HelpButton,
    extractProps: ({ attrs }) => ({ topic: attrs.topic }),
    additionalClasses: ["d-inline"],
});
