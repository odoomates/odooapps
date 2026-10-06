import { registry } from "@web/core/registry";

// Adding existing users to a profile from the profile itself.
registry.category("web_tour.tours").add("om_access_manager_add_users", {
    steps: () => [
        {
            content: "type a user's name",
            trigger: '.o_field_widget[name="user_ids"] input',
            run: "edit om_add_users_target",
        },
        {
            content: "only existing users: no way to create one here",
            trigger: '.o-autocomplete--dropdown-item:contains("om_add_users_target")',
            run() {
                if ([...document.querySelectorAll(".o-autocomplete--dropdown-item")]
                        .some((item) => /Create/.test(item.textContent))) {
                    throw new Error("the dropdown offers to create a user");
                }
            },
        },
        {
            content: "pick the user",
            trigger: '.o-autocomplete--dropdown-item:contains("om_add_users_target") a',
            run: "click",
        },
        {
            content: "the user is a tag",
            trigger: '.o_field_widget[name="user_ids"] .o_tag:contains("om_add_users_target")',
        },
        {
            content: "save",
            trigger: ".o_form_button_save",
            run: "click",
        },
        {
            content: "saved",
            trigger: ".o_form_saved",
        },
    ],
});
