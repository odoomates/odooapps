/** @odoo-module **/

import tour from "web_tour.tour";

// Adding existing users to a profile from the profile itself.
tour.register("om_access_manager_add_users", {
    test: true,
}, [
    {
        content: "edit the profile (Odoo 15 opens it read only)",
        trigger: ".o_form_button_edit",
        run: "click",
    },
    {
        content: "type a user's name",
        trigger: '.o_field_widget[name="user_ids"] input',
        run: "text om_add_users_target",
    },
    {
        content: "only existing users: no way to create one here",
        trigger: '.ui-autocomplete .ui-menu-item a:contains("om_add_users_target")',
        run() {
            if ([...document.querySelectorAll(".ui-autocomplete .ui-menu-item")]
                    .some((item) => /Create/.test(item.textContent))) {
                throw new Error("the dropdown offers to create a user");
            }
        },
    },
    {
        content: "pick the user",
        trigger: '.ui-autocomplete .ui-menu-item a:contains("om_add_users_target")',
        run: "click",
    },
    {
        content: "the user is a tag",
        trigger: '.o_field_widget[name="user_ids"] .o_tag_badge_text:contains("om_add_users_target")',
        run() {},
    },
    {
        content: "save",
        trigger: ".o_form_button_save",
        run: "click",
    },
    {
        content: "saved",
        trigger: ".o_form_view.o_form_readonly",
        run() {},
    },
]);
