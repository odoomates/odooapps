import { registry } from "@web/core/registry";

/**
 * Drives customize mode end to end: switch it on from the navbar, pick a field,
 * rename it and confirm the rename reached the rendered form.
 */
registry.category("web_tour.tours").add("om_pen_tour", {
    steps: () => [
        {
            content: "the partner form is open",
            trigger: ".o_form_view .o_field_widget[name='function']",
        },
        {
            content: "turn customize mode on from the navbar",
            trigger: ".o_om_pen_toggle",
            run: "click",
        },
        {
            content: "the banner says which view is being customized",
            trigger: ".o_om_pen_banner:contains('res.partner')",
        },
        {
            content: "the View tab holds the action switches",
            trigger: ".om-pen-tabs button:contains('View')",
            run: "click",
        },
        {
            content: "the action switches are there",
            trigger: ".om-pen-check:contains('Create records') input",
        },
        {
            content: "back to the Field tab",
            trigger: ".om-pen-tabs button:contains('Field')",
            run: "click",
        },
        {
            content: "clicking a field selects it instead of editing the record",
            trigger: ".o_form_view .o_field_widget[name='function']",
            run: "click",
        },
        {
            content: "the panel now describes that field",
            trigger: ".om-pen-head code:contains('function')",
        },
        {
            content: "rename it",
            trigger: ".om-pen-field-label",
            run: "edit Role On Site",
        },
        {
            content: "apply",
            trigger: ".om-pen-foot .btn-primary",
            run: "click",
        },
        {
            content: "publish so the change goes live",
            trigger: ".o_om_pen_banner button:contains('Publish')",
            run: "click",
        },
        {
            content: "wait for the publish to finish before looking at the result",
            trigger: ".o_om_pen_banner:not(:has(.om-pen-draft-count, .om-pen-saving))",
        },
        {
            content: "the form re-rendered with the new label, without a page reload",
            trigger: ".o_form_view .o_form_label:contains('Role On Site')",
        },
        {
            content: "leave customize mode",
            trigger: ".o_om_pen_banner .om-pen-exit",
            run: "click",
        },
        {
            content: "the banner is gone and the label survived",
            trigger: ".o_form_view .o_form_label:contains('Role On Site')",
        },
    ],
});

/**
 * Adds a field that is not yet on the view: the floating button, the dialog, then
 * clicking the field it should sit after.
 */
registry.category("web_tour.tours").add("om_pen_add_field_tour", {
    steps: () => [
        {
            content: "the cut-down form is open",
            trigger: ".o_form_view .o_field_widget[name='function']",
        },
        {
            content: "turn customize mode on",
            trigger: ".o_om_pen_toggle",
            run: "click",
        },
        {
            content: "open the add-field dialog from the Field tab",
            trigger: ".om-pen-add-field",
            run: "click",
        },
        {
            content: "the Add tab offers the dialog for more options",
            trigger: ".om-pen-palette-wrap button:contains('more options')",
            run: "click",
        },
        {
            content: "switch to picking an existing field",
            trigger: ".om-pen-modes button:contains('Existing field')",
            run: "click",
        },
        {
            content: "search for the field",
            trigger: ".modal input[placeholder='Search fields…']",
            run: "edit website",
        },
        {
            content: "pick it from the filtered list",
            trigger: ".o_om_pen_fieldrow[data-field='website']",
            run: "click",
        },
        {
            content: "the row shows it is selected",
            trigger: ".o_om_pen_fieldrow.selected[data-field='website'] .fa-check-circle",
        },
        {
            content: "and the dialog spells out what is picked",
            trigger: ".om-pen-picked.has:contains('website')",
        },
        {
            content: "clicking the picked row again lets go of it",
            trigger: ".o_om_pen_fieldrow.selected[data-field='website']",
            run: "click",
        },
        {
            content: "nothing is picked, and the dialog says so",
            trigger: ".modal .om-pen-picked:not(.has)",
        },
        {
            content: "confirming is not offered with nothing picked",
            trigger: ".modal .btn-primary[disabled]",
        },
        {
            content: "pick it again to carry on",
            trigger: ".o_om_pen_fieldrow[data-field='website']",
            run: "click",
        },
        {
            content: "confirm",
            trigger: ".modal .btn-primary",
            run: "click",
        },
        {
            content: "the dialog closed",
            trigger: "body:not(:has(.modal))",
        },
        {
            content: "the banner now asks where to put it",
            trigger: ".o_om_pen_banner:contains('website')",
        },
        {
            content: "click the field it should follow",
            trigger: ".o_form_view .o_field_widget[name='function']",
            run: "click",
        },
        {
            content: "publish so the change goes live",
            trigger: ".o_om_pen_banner button:contains('Publish')",
            run: "click",
        },
        {
            content: "wait for the publish to finish before looking at the result",
            trigger: ".o_om_pen_banner:not(:has(.om-pen-draft-count, .om-pen-saving))",
        },
        {
            content: "the field is on the form now",
            trigger: ".o_form_view .o_field_widget[name='website']",
        },
        {
            content: "the panel selected it and offers to take it off again",
            trigger: ".om-pen-foot .text-danger:contains('Remove from view')",
        },
        {
            content: "Apply is disabled while nothing has been changed, so an idle click"
                + " cannot undo the add",
            trigger: ".om-pen-foot .btn-primary[disabled]",
        },
        {
            content: "the field is still there",
            trigger: ".o_form_view .o_field_widget[name='website']",
        },
    ],
});

/** Drags a field onto another one and checks the view really reordered. */
registry.category("web_tour.tours").add("om_pen_drag_tour", {
    steps: () => [
        {
            content: "the three-field form is open",
            trigger: ".o_form_view .o_field_widget[name='comment']",
        },
        {
            content: "turn customize mode on",
            trigger: ".o_om_pen_toggle",
            run: "click",
        },
        {
            content: "wait for customize mode to be on before dragging",
            trigger: ".o_om_pen_banner",
        },
        {
            content: "drag the first field onto the last one",
            trigger: ".o_form_view .o_field_widget[name='function']",
            run: "drag_and_drop .o_form_view .o_field_widget[name='comment']",
        },
        {
            content: "publish so the change goes live",
            trigger: ".o_om_pen_banner button:contains('Publish')",
            run: "click",
        },
        {
            content: "wait for the publish to finish before looking at the result",
            trigger: ".o_om_pen_banner:not(:has(.om-pen-draft-count, .om-pen-saving))",
        },
        {
            content: "the dragged field is now marked as customized",
            trigger: ".o_field_widget[name='function'].o_om_pen_touched",
        },
        {
            content: "the Changes tab records it",
            trigger: ".om-pen-tabs button:contains('Changes')",
            run: "click",
        },
        {
            content: "and it says it moved",
            trigger: ".om-pen-change:contains('moved')",
        },
    ],
});

/** Drags a field onto a notebook tab, which drops it inside that page. */
registry.category("web_tour.tours").add("om_pen_page_drop_tour", {
    steps: () => [
        {
            content: "the form with a notebook is open",
            trigger: ".o_notebook .nav-link[name='contacts']",
        },
        {
            content: "turn customize mode on",
            trigger: ".o_om_pen_toggle",
            run: "click",
        },
        {
            content: "wait for customize mode to be on before dragging",
            trigger: ".o_om_pen_banner",
        },
        {
            content: "drag a field onto the page tab",
            trigger: ".o_form_view .o_field_widget[name='function']",
            run: "drag_and_drop .o_notebook .nav-link[name='contacts']",
        },
        {
            content: "publish so the change goes live",
            trigger: ".o_om_pen_banner button:contains('Publish')",
            run: "click",
        },
        {
            content: "wait for the publish to finish before looking at the result",
            trigger: ".o_om_pen_banner:not(:has(.om-pen-draft-count, .om-pen-saving))",
        },
        {
            content: "the Changes tab records it",
            trigger: ".om-pen-tabs button:contains('Changes')",
            run: "click",
        },
        {
            content: "and the field is marked as customized",
            trigger: ".om-pen-change:contains('Job Position')",
        },
    ],
});

/** Adds a field to the list embedded in a one2many. */
registry.category("web_tour.tours").add("om_pen_subview_tour", {
    steps: () => [
        {
            content: "the form with an embedded list is open",
            trigger: ".o_field_widget[name='child_ids']",
        },
        {
            content: "turn customize mode on",
            trigger: ".o_om_pen_toggle",
            run: "click",
        },
        {
            content: "the View tab lists the embedded views",
            trigger: ".om-pen-tabs button:contains('View')",
            run: "click",
        },
        {
            content: "add a field to the embedded list",
            trigger: ".om-pen-card button:contains('Add to list')",
            run: "click",
        },
        {
            content: "the dialog is scoped to the linked model",
            trigger: ".modal .modal-title:contains('list')",
        },
        {
            content: "switch to picking an existing field",
            trigger: ".om-pen-modes button:contains('Existing field')",
            run: "click",
        },
        {
            content: "search for a field of the linked model",
            trigger: ".modal input[placeholder='Search fields…']",
            run: "edit email",
        },
        {
            content: "pick it",
            trigger: ".o_om_pen_fieldrow[data-field='email']",
            run: "click",
        },
        {
            content: "add it",
            trigger: ".modal .btn-primary",
            run: "click",
        },
        {
            content: "publish so the change goes live",
            trigger: ".o_om_pen_banner button:contains('Publish')",
            run: "click",
        },
        {
            content: "wait for the publish to finish before looking at the result",
            trigger: ".o_om_pen_banner:not(:has(.om-pen-draft-count, .om-pen-saving))",
        },
        {
            content: "the column is on the embedded list now",
            trigger: ".o_field_widget[name='child_ids'] th[data-name='email']",
        },
    ],
});

/** The unsaved-changes affordances: the footer, Ctrl+Enter, and the guard on leaving. */
registry.category("web_tour.tours").add("om_pen_unsaved_tour", {
    steps: () => [
        {
            content: "the form is open",
            trigger: ".o_form_view .o_field_widget[name='function']",
        },
        {
            content: "turn customize mode on",
            trigger: ".o_om_pen_toggle",
            run: "click",
        },
        {
            content: "wait for customize mode",
            trigger: ".o_om_pen_banner",
        },
        {
            content: "pick a field",
            trigger: ".o_form_view .o_field_widget[name='function']",
            run: "click",
        },
        {
            content: "the label box starts on the label the field actually shows",
            trigger: ".om-pen-field-label:value(Job Position)",
        },
        {
            content: "Apply is disabled while nothing has changed",
            trigger: ".om-pen-foot .btn-primary[disabled]",
        },
        {
            content: "change the label",
            trigger: ".om-pen-field-label",
            run: "edit Role",
        },
        {
            content: "the footer says there is something pending",
            trigger: ".om-pen-foot.dirty .om-pen-pending",
        },
        {
            content: "apply with the keyboard",
            trigger: ".om-pen-field-label",
            run: "press ctrl+Enter",
        },
        {
            content: "the footer is settled again once the edit has been applied",
            trigger: ".om-pen-foot:not(.dirty) .btn-primary[disabled]",
        },
        {
            content: "leaving now must not ask anything: the work is stored as a draft",
            trigger: ".o_om_pen_banner .om-pen-exit",
            run: "click",
        },
        {
            content: "customize mode closed without a prompt",
            trigger: "body:not(:has(.o_om_pen_banner)):not(:has(.modal))",
        },
        {
            content: "go back in",
            trigger: ".o_om_pen_toggle",
            run: "click",
        },
        {
            content: "wait for customize mode",
            trigger: ".o_om_pen_banner",
        },
        {
            content: "pick the field again",
            trigger: ".o_form_view .o_field_widget[name='function']",
            run: "click",
        },
        {
            content: "the applied value came back from the server",
            trigger: ".om-pen-field-label:value(Role)",
        },
        {
            content: "start an edit and do not apply it",
            trigger: ".om-pen-field-label",
            run: "edit Role Again",
        },
        {
            content: "try to leave",
            trigger: ".o_om_pen_banner .om-pen-exit",
            run: "click",
        },
        {
            content: "this time leaving is guarded",
            trigger: ".modal:contains('Unsaved changes')",
        },
        {
            content: "discard",
            trigger: ".modal .btn-danger",
            run: "click",
        },
        {
            content: "customize mode is off",
            trigger: "body:not(:has(.o_om_pen_banner))",
        },
    ],
});

registry.category("web_tour.tours").add("om_pen_new_field_tour", {
    steps: () => [
        {
            content: "the form is open",
            trigger: ".o_form_view .o_field_widget[name='function']",
        },
        {
            content: "turn customize mode on",
            trigger: ".o_om_pen_toggle",
            run: "click",
        },
        {
            content: "wait for customize mode",
            trigger: ".o_om_pen_banner",
        },
        {
            content: "open the dialog",
            trigger: ".om-pen-add-field",
            run: "click",
        },
        {
            content: "the Add tab offers the dialog for more options",
            trigger: ".om-pen-palette-wrap button:contains('more options')",
            run: "click",
        },
        {
            content: "it opens on New field",
            trigger: ".om-pen-modes button.active:contains('New field')",
        },
        {
            content: "type a label",
            trigger: ".om-pen-new-label",
            run: "edit Internal Reference",
        },
        {
            content: "the technical name follows the label",
            trigger: ".om-pen-new-name:value(internal_reference)",
        },
        {
            content: "take the technical name over",
            trigger: ".om-pen-new-name",
            run: "edit our_ref",
        },
        {
            content: "pick a type",
            trigger: ".om-pen-types button:contains('Multiline Text')",
            run: "click",
        },
        {
            content: "create it",
            trigger: ".modal .btn-primary",
            run: "click",
        },
        {
            content: "now say where it goes",
            trigger: ".o_form_view .o_field_widget[name='function']",
            run: "click",
        },
        {
            content: "publish",
            trigger: ".o_om_pen_banner button:contains('Publish')",
            run: "click",
        },
        {
            content: "wait for the publish to finish",
            trigger: ".o_om_pen_banner:not(:has(.om-pen-draft-count, .om-pen-saving))",
        },
        {
            content: "the new field is on the form under its chosen name",
            trigger: ".o_form_view .o_field_widget[name='x_our_ref']",
        },
    ],
});

/** Builds a related field by following a link, and checks it renders the linked value. */
registry.category("web_tour.tours").add("om_pen_related_tour", {
    steps: () => [
        {
            content: "the form is open",
            trigger: ".o_form_view .o_field_widget[name='function']",
        },
        {
            content: "turn customize mode on",
            trigger: ".o_om_pen_toggle",
            run: "click",
        },
        {
            content: "wait for customize mode",
            trigger: ".o_om_pen_banner",
        },
        {
            content: "open the dialog",
            trigger: ".om-pen-add-field",
            run: "click",
        },
        {
            content: "the Add tab offers the dialog for more options",
            trigger: ".om-pen-palette-wrap button:contains('more options')",
            run: "click",
        },
        {
            content: "switch to a related field",
            trigger: ".om-pen-modes button:contains('Related field')",
            run: "click",
        },
        {
            content: "follow the parent link",
            trigger: ".om-pen-hop[data-level='0']",
            run: "select parent_id",
        },
        {
            content: "then take its website",
            trigger: ".om-pen-hop[data-level='1']",
            run: "select website",
        },
        {
            content: "the dialog says what the path lands on",
            trigger: ".om-pen-picked.has:contains('parent_id.website')",
        },
        {
            content: "name it",
            trigger: ".om-pen-new-name",
            run: "edit parent_site",
        },
        {
            content: "create it",
            trigger: ".modal .btn-primary",
            run: "click",
        },
        {
            content: "say where it goes",
            trigger: ".o_form_view .o_field_widget[name='function']",
            run: "click",
        },
        {
            content: "publish",
            trigger: ".o_om_pen_banner button:contains('Publish')",
            run: "click",
        },
        {
            content: "wait for the publish to finish",
            trigger: ".o_om_pen_banner:not(:has(.om-pen-draft-count, .om-pen-saving))",
        },
        {
            content: "the mirrored field shows the linked record's value",
            trigger: ".o_form_view .o_field_widget[name='x_parent_site']:contains('example.com')",
        },
    ],
});

/** Builds a condition from rows instead of typing python. */
registry.category("web_tour.tours").add("om_pen_condition_tour", {
    steps: () => [
        {
            content: "the form is open",
            trigger: ".o_form_view .o_field_widget[name='function']",
        },
        {
            content: "turn customize mode on",
            trigger: ".o_om_pen_toggle",
            run: "click",
        },
        {
            content: "wait for customize mode",
            trigger: ".o_om_pen_banner",
        },
        {
            content: "pick a field",
            trigger: ".o_form_view .o_field_widget[name='function']",
            run: "click",
        },
        {
            content: "hide it under a condition",
            trigger: ".om-pen-row:contains('Hidden') .om-pen-segmented button:contains('If')",
            run: "click",
        },
        {
            content: "the builder is offered, not a python box",
            trigger: ".om-pen-cond .om-pen-cond-add",
            run: "click",
        },
        {
            content: "choose the field the condition looks at",
            trigger: ".om-pen-cond-field",
            run: "select website",
        },
        {
            content: "choose an operator that needs no value",
            trigger: ".om-pen-cond-op",
            run: "select not set",
        },
        {
            content: "apply",
            trigger: ".om-pen-foot .btn-primary",
            run: "click",
        },
        {
            content: "publish",
            trigger: ".o_om_pen_banner button:contains('Publish')",
            run: "click",
        },
        {
            content: "wait for the publish to finish",
            trigger: ".o_om_pen_banner:not(:has(.om-pen-draft-count, .om-pen-saving))",
        },
        {
            content: "the condition survived as rows, not as raw text",
            trigger: ".om-pen-cond .om-pen-cond-field",
        },
    ],
});
