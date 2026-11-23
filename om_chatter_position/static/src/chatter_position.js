/** @odoo-module **/

import { session } from "@web/session";

/**
 * Where the chatter sits on a form, chosen by each user in My Preferences.
 *
 * The layout itself is done in CSS (chatter_position.scss), under a class on the
 * page: Automatic puts the chatter beside the sheet once the screen is extra wide,
 * "Below the form" keeps it underneath whatever the screen, and "Beside the form"
 * keeps it next to the sheet from a large screen (992 pixels) up.
 */
const position = session.om_chatter_position || "auto";
document.documentElement.classList.toggle("o_om_chatter_below", position === "bottom");
document.documentElement.classList.toggle("o_om_chatter_side", position === "side");
