import { _t } from "@web/core/l10n/translation";

/**
 * Settings of the view itself, shown in the View tab. Each one is an attribute of
 * the root node of the arch.
 *
 * type: bool (a switch), select (fixed choices), field (a field of the model),
 * text or number.
 */
export const VIEW_SETTINGS = {
    form: [
        { attr: "create", label: _t("Can create"), type: "bool", default: true },
        { attr: "edit", label: _t("Can edit"), type: "bool", default: true },
        { attr: "delete", label: _t("Can delete"), type: "bool", default: true },
        { attr: "duplicate", label: _t("Can duplicate"), type: "bool", default: true },
    ],
    list: [
        {
            attr: "editable",
            label: _t("Edit in the list"),
            type: "select",
            choices: [["", _t("No, open the form")], ["top", _t("Yes, new lines on top")], ["bottom", _t("Yes, new lines at the bottom")]],
        },
        { attr: "create", label: _t("Can create"), type: "bool", default: true },
        { attr: "edit", label: _t("Can edit"), type: "bool", default: true },
        { attr: "delete", label: _t("Can delete"), type: "bool", default: true },
        { attr: "multi_edit", label: _t("Edit several records at once"), type: "bool" },
        { attr: "open_form_view", label: _t("Open the form from an editable line"), type: "bool" },
        { attr: "export_xlsx", label: _t("Can export"), type: "bool", default: true },
        { attr: "import", label: _t("Can import"), type: "bool", default: true },
        { attr: "default_order", label: _t("Sort by"), type: "order" },
        { attr: "limit", label: _t("Records per page"), type: "number" },
    ],
    kanban: [
        { attr: "default_group_by", label: _t("Columns by"), type: "field", fieldTypes: ["many2one", "selection", "boolean", "char", "date", "datetime", "many2many"] },
        { attr: "quick_create", label: _t("Quick create in a column"), type: "bool", default: true },
        { attr: "records_draggable", label: _t("Drag cards between columns"), type: "bool", default: true },
        { attr: "group_create", label: _t("Add columns"), type: "bool", default: true },
        { attr: "create", label: _t("Can create"), type: "bool", default: true },
        { attr: "edit", label: _t("Can edit"), type: "bool", default: true },
        { attr: "delete", label: _t("Can delete"), type: "bool", default: true },
        { attr: "default_order", label: _t("Sort by"), type: "order" },
        { attr: "highlight_color", label: _t("Card colour"), type: "field", fieldTypes: ["integer"] },
    ],
    calendar: [
        { attr: "date_start", label: _t("Start date"), type: "field", fieldTypes: ["date", "datetime"] },
        { attr: "date_stop", label: _t("End date"), type: "field", fieldTypes: ["date", "datetime"] },
        { attr: "date_delay", label: _t("Duration"), type: "field", fieldTypes: ["float", "integer"] },
        { attr: "all_day", label: _t("All day"), type: "field", fieldTypes: ["boolean"] },
        { attr: "color", label: _t("Colour by"), type: "field", fieldTypes: ["many2one", "selection", "integer"] },
        {
            attr: "mode",
            label: _t("Default scale"),
            type: "select",
            choices: [["", _t("Week")], ["day", _t("Day")], ["month", _t("Month")], ["year", _t("Year")]],
        },
        { attr: "quick_create", label: _t("Quick create"), type: "bool", default: true },
        { attr: "event_open_popup", label: _t("Open events in a dialog"), type: "bool" },
        { attr: "create", label: _t("Can create"), type: "bool", default: true },
        { attr: "delete", label: _t("Can delete"), type: "bool", default: true },
    ],
    pivot: [
        { attr: "disable_linking", label: _t("Do not open records from a cell"), type: "bool" },
        { attr: "display_quantity", label: _t("Show the count"), type: "bool" },
    ],
    graph: [
        {
            attr: "type",
            label: _t("Chart"),
            type: "select",
            choices: [["", _t("Bar")], ["line", _t("Line")], ["pie", _t("Pie")]],
        },
        { attr: "stacked", label: _t("Stacked"), type: "bool", default: true },
        {
            attr: "order",
            label: _t("Order"),
            type: "select",
            choices: [["", _t("As grouped")], ["asc", _t("Ascending")], ["desc", _t("Descending")]],
        },
        { attr: "disable_linking", label: _t("Do not open records from the chart"), type: "bool" },
    ],
    activity: [],
    search: [],
};
