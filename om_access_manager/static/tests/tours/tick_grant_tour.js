/** @odoo-module **/

import { registry } from "@web/core/registry";

// Ticking an app its users cannot open gives it to them, unticking takes it back.
registry.category("web_tour.tours").add("om_access_manager_tick_grant", {
    test: true,
    steps: () => [
        {
            content: "open the menu tree",
            trigger: ".o_notebook .nav-link:contains(Menus)",
            run: "click",
        },
        {
            content: "the app is not given: shown unticked",
            trigger: ".o_om_menu_tree_row:contains(OM Tick App) .o_om_not_given",
            isCheck: true,
        },
        {
            content: "tick it",
            trigger: ".o_om_menu_tree_row:contains(OM Tick App) input[type=checkbox]",
            run: "click",
        },
        {
            content: "given: ticked, and granted",
            trigger: '.o_field_widget[name="granted_group_ids"] .o_tag:contains(OM Tick App / User)',
            isCheck: true,
        },
        {
            content: "no longer marked",
            trigger: ".o_om_menu_tree_row:contains(OM Tick App):not(:has(.o_om_not_given)) input[type=checkbox]:checked",
            isCheck: true,
        },
        {
            content: "save",
            trigger: ".o_form_button_save",
            run: "click",
        },
        {
            content: "saved",
            trigger: ".o_form_saved",
            isCheck: true,
        },
    ],
});

registry.category("web_tour.tours").add("om_access_manager_untick_grant", {
    test: true,
    steps: () => [
        {
            content: "open the menu tree",
            trigger: ".o_notebook .nav-link:contains(Menus)",
            run: "click",
        },
        {
            content: "untick the app the profile gives",
            trigger: ".o_om_menu_tree_row:contains(OM Tick App) input[type=checkbox]:checked",
            run: "click",
        },
        {
            content: "the grant is gone",
            trigger: '.o_field_widget[name="granted_group_ids"]:not(:has(.o_tag:contains(OM Tick App)))',
            isCheck: true,
        },
        {
            content: "save",
            trigger: ".o_form_button_save",
            run: "click",
        },
        {
            content: "saved",
            trigger: ".o_form_saved",
            isCheck: true,
        },
    ],
});
