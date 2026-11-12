import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("om_theme_launcher_tour", {
    steps: () => [
        {
            content: "the launcher lists apps, each with its icon",
            trigger: ".om-launcher .om-app .om-app-icon",
        },
        {
            content: "the search box is out of the way until it is needed",
            // anchored on the launcher, not the box: a hidden element is not a
            // valid trigger, which is itself part of what this asserts
            trigger: ".om-launcher",
            run() {
                // asserting the computed style, not just the class: a class that
                // no rule acts on would leave the box on screen
                const box = document.querySelector(".om-launcher-search");
                if (getComputedStyle(box).visibility !== "hidden") {
                    throw new Error("the search box is showing before anyone typed");
                }
                // ...but it must still hold its space, or revealing it shoves the
                // app grid down the page
                if (box.getBoundingClientRect().height < 20) {
                    throw new Error("the hidden search box collapsed the layout");
                }
            },
        },
        {
            content: "typing anywhere on the home screen reveals it",
            trigger: ".om-launcher",
            run() {
                document.dispatchEvent(new KeyboardEvent("keydown", { key: "s", bubbles: true }));
            },
        },
        {
            content: "and the first keystroke is not swallowed",
            trigger: ".om-launcher-search.om-visible input:value(s)",
        },
        {
            content: "the box takes focus, so typing carries on into it",
            trigger: ".om-launcher-search.om-visible input",
            run() {
                const input = document.querySelector(".om-launcher-search input");
                if (document.activeElement !== input) {
                    throw new Error(
                        `the search box never took focus: <${document.activeElement.tagName}>`
                    );
                }
            },
        },
        {
            content: "and if focus is lost, typing still lands instead of sticking",
            trigger: ".om-launcher",
            run() {
                // The bug was that the handler gave up once a query existed, so any
                // keystroke arriving at the document - which is exactly what happens
                // when the box does not hold focus - went nowhere and the search
                // froze on its first character.
                document.querySelector(".om-launcher-search input").blur();
                document.dispatchEvent(new KeyboardEvent("keydown", { key: "e", bubbles: true }));
            },
        },
        {
            trigger: ".om-launcher-search input:value(se)",
        },
        {
            content: "backspace works from the document too",
            trigger: ".om-launcher",
            run() {
                document.querySelector(".om-launcher-search input").blur();
                document.dispatchEvent(
                    new KeyboardEvent("keydown", { key: "Backspace", bubbles: true })
                );
            },
        },
        {
            trigger: ".om-launcher-search input:value(s)",
        },
        {
            content: "searching narrows the grid",
            trigger: ".om-launcher-search input",
            run: "edit settings",
        },
        {
            content: "only the matching app is left",
            trigger: ".om-launcher-grid:has(.om-app-name:contains('Settings'))",
        },
        {
            trigger: ".om-launcher-grid:not(:has(.om-app-name:contains('Contacts')))",
        },
        {
            content: "the search reaches menu items inside an app, not only app names",
            trigger: ".om-launcher-search input",
            run: "edit users",
        },
        {
            content: "'Users' lives inside Settings, so it is found through its app",
            trigger: ".om-app-item:contains('Users')",
            run: "click",
        },
        {
            content: "clicking a matched menu item opens it",
            trigger: ".o_breadcrumb:contains('Users')",
        },
    ],
});

registry.category("web_tour.tours").add("om_theme_launcher_open_app_tour", {
    steps: () => [
        {
            content: "clicking a tile opens the app",
            trigger: ".om-launcher .om-app:has(.om-app-name:contains('Settings'))",
            run: "click",
        },
        {
            trigger: ".o_control_panel",
        },
        {
            content: "the apps button is styled like a navbar entry, not a raw button",
            trigger: ".o_navbar_apps_menu .om-navbar-apps",
            run() {
                const btn = document.querySelector(".o_navbar_apps_menu .om-navbar-apps");
                const bar = document.querySelector(".o_main_navbar");
                const bg = getComputedStyle(btn).backgroundColor;
                // it either sits on the navbar surface or carries a translucent
                // hover/focus overlay - what it must never be is the opaque grey a
                // browser gives an unstyled <button>
                const overlay = bg.startsWith("rgba(") && !/,\s*1\)$/.test(bg);
                if (bg !== getComputedStyle(bar).backgroundColor && !overlay) {
                    throw new Error(`the apps button fell back to browser chrome: ${bg}`);
                }
            },
        },
        {
            content: "the apps button goes back to the launcher, not to the sidebar",
            trigger: ".o_navbar_apps_menu button",
            run: "click",
        },
        {
            trigger: ".om-launcher .om-app",
        },
        {
            content: "and it opened the launcher rather than the app menu sidebar",
            trigger: "body:not(:has(.o_app_menu_sidebar))",
        },
        {
            content: "the app we came from is no longer advertised in the navbar",
            trigger: ".o_main_navbar:not(:has(.o_menu_brand))",
        },
        {
            content: "nothing divides the navbar from the screen below it",
            trigger: ".o_main_navbar",
            run() {
                const bar = document.querySelector(".o_main_navbar");
                const cs = getComputedStyle(bar);
                if (parseFloat(cs.borderBottomWidth) > 0 && cs.borderBottomStyle !== "none") {
                    throw new Error(`the navbar still has a divider: ${cs.borderBottom}`);
                }
                if (cs.boxShadow !== "none") {
                    throw new Error(`the navbar still casts a shadow: ${cs.boxShadow}`);
                }
                // and it is the same surface as the launcher behind it
                const launcher = getComputedStyle(document.querySelector(".om-launcher"));
                if (cs.backgroundColor !== launcher.backgroundColor) {
                    throw new Error(
                        `navbar ${cs.backgroundColor} does not match the launcher ${launcher.backgroundColor}`
                    );
                }
            },
        },
        {
            content: "on the home screen the apps button, which would only reopen it, is hidden",
            trigger: ".o_navbar_apps_menu:not(:visible)",
        },
        {
            trigger: ".o_main_navbar:not(:has(.o_menu_sections))",
        },
    ],
});

registry.category("web_tour.tours").add("om_theme_palette_tour", {
    steps: () => [
        {
            content: "the theme leaves the search bar's pill intact",
            trigger: ".o_cp_searchview .o_searchview",
            run() {
                // Odoo builds the search bar as an input-group whose children inherit
                // the group's radius; Bootstrap then squares the corners that face
                // inwards. .o_searchview is the first child, so it owns the left,
                // magnifier end of the pill and its right corners are meant to be 0.
                // A blanket radius on it squares off that left end.
                const group = document.querySelector(".o_cp_searchview");
                const view = document.querySelector(".o_cp_searchview .o_searchview");
                const want = getComputedStyle(group).borderTopLeftRadius;
                const got = getComputedStyle(view).borderTopLeftRadius;
                if (got !== want) {
                    throw new Error(`the search pill is squared off: ${got} vs group ${want}`);
                }
            },
        },
        {
            content: "the palette reaches Odoo's own buttons, not only our stylesheet",
            trigger: ".o_control_panel .btn-primary",
            run() {
                const btn = document.querySelector(".o_control_panel .btn-primary");
                const primary = getComputedStyle(document.documentElement)
                    .getPropertyValue("--om-theme-primary")
                    .trim();
                const probe = document.createElement("span");
                probe.style.color = primary;
                document.body.appendChild(probe);
                const expected = getComputedStyle(probe).color;
                probe.remove();
                const bg = getComputedStyle(btn).backgroundColor;
                if (bg !== expected) {
                    throw new Error(`the button is not on the theme colour: ${bg} vs ${expected}`);
                }
                const mean = (c) => c.match(/\d+/g).slice(0, 3).reduce((a, b) => a + +b, 0) / 3;
                if (Math.abs(mean(getComputedStyle(btn).color) - mean(bg)) < 90) {
                    throw new Error("button text is not readable on the primary colour");
                }
            },
        },
    ],
});
