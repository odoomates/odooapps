/** @odoo-module **/

import { registry } from "@web/core/registry";
import { session } from "@web/session";

/**
 * The switches of the search bar and the forms (no custom filters, no saved
 * searches...): a class on the body, read by search_parts.scss. What writes
 * is also refused on the server.
 */
registry.category("services").add("om_access_body_classes", {
    start() {
        const classes = session.om_access_classes || [];
        if (classes.length) {
            document.body.classList.add(...classes);
        }
    },
});
