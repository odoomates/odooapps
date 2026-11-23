import { registry } from "@web/core/registry";

/**
 * Open the Studio from the navbar, rename a field of the form, check the draft shows
 * it, publish, and come back to the live form.
 */
registry.category("web_tour.tours").add("om_pen_studio_rename_tour", {
    steps: () => [
        {
            content: "the partner form is open",
            trigger: ".o_form_view .o_field_widget[name='function']",
        },
        {
            content: "open the Studio from the navbar",
            trigger: ".o_om_pen_toggle",
            run: "click",
        },
        {
            content: "the Studio shows the form on its canvas",
            trigger: ".o_pen_canvas .o_form_view .o_field_widget[name='function']",
        },
        {
            content: "clicking a field selects it instead of editing the record",
            trigger: ".o_pen_canvas .o_field_widget[name='function']",
            run: "click",
        },
        {
            content: "its properties are shown",
            trigger: ".o_pen_prop_head:contains('field')",
        },
        {
            content: "rename it",
            trigger: ".o_pen_input_string",
            run: "edit Role On Site",
        },
        {
            content: "leave the box: the change is applied",
            trigger: ".o_pen_prop_head",
            run: "click",
        },
        {
            content: "the draft has one change",
            trigger: ".o_pen_draft_badge:contains('1 unpublished')",
        },
        {
            content: "the canvas shows the new label",
            trigger: ".o_pen_canvas .o_form_view:contains('Role On Site')",
        },
        {
            content: "publish",
            trigger: ".o_pen_publish",
            run: "click",
        },
        {
            content: "the view is live",
            trigger: ".o_pen_live_badge",
        },
        {
            content: "close the Studio",
            trigger: ".o_pen_close",
            run: "click",
        },
        {
            content: "the live form shows the new label",
            trigger: ".o_action_manager .o_form_view:contains('Role On Site')",
        },
    ],
});

/**
 * Build an app from the Studio and land on its form, ready to be changed.
 */
registry.category("web_tour.tours").add("om_pen_studio_app_tour", {
    steps: () => [
        {
            content: "open the Studio from the navbar",
            trigger: ".o_om_pen_toggle",
            run: "click",
        },
        {
            content: "go to the app builder",
            trigger: ".o_pen_section[data-section='apps']",
            run: "click",
        },
        {
            content: "name the app",
            trigger: ".o_pen_app_name",
            run: "edit Tour Fleet",
        },
        {
            content: "name its records",
            trigger: ".o_pen_model_label",
            run: "edit Tour Vehicle",
        },
        {
            content: "with tags",
            trigger: ".o_pen_feature[data-feature='tags'] input",
            run: "click",
        },
        {
            content: "create it",
            trigger: ".o_pen_create_app:enabled",
            run: "click",
        },
        {
            content: "the Studio opens on the new model's form",
            trigger: ".o_pen_model:contains('Tour Vehicle')",
        },
        {
            content: "with its stages in the header",
            trigger: ".o_pen_canvas .o_form_view .o_statusbar_status",
        },
        {
            content: "and its menus can be edited",
            trigger: ".o_pen_section[data-section='menus']",
            run: "click",
        },
        {
            content: "the app's menus are listed",
            trigger: ".o_pen_menu_table tr[data-menu='Tour Vehicle']",
        },
    ],
});
