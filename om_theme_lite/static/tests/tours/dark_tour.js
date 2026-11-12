import { registry } from "@web/core/registry";

/** Mean channel value of a computed "rgb(r, g, b)" colour. */
function brightness(colour) {
    const [r, g, b] = colour.match(/\d+/g).map(Number);
    return (r + g + b) / 3;
}

registry.category("web_tour.tours").add("om_theme_dark_tour", {
    steps: () => [
        {
            content: "the dark bundle is the one that got served",
            trigger: ".o_control_panel .btn-primary",
            run() {
                const bg = getComputedStyle(document.body).backgroundColor;
                if (brightness(bg) > 90) {
                    throw new Error(`body is not dark: ${bg}`);
                }
                const text = getComputedStyle(document.body).color;
                if (brightness(text) < 150) {
                    throw new Error(`text did not lighten: ${text}`);
                }
                // the palette still has to survive the flip
                const primary = getComputedStyle(document.documentElement)
                    .getPropertyValue("--om-theme-primary")
                    .trim();
                if (!primary) {
                    throw new Error("the palette is missing in dark mode");
                }
                // Odoo's "primary" button takes its text colour from $o-white, which
                // is a dark surface here. What matters is that the label contrasts
                // with the fill - not which of the two is the lighter one, since the
                // accent inverts between the schemes.
                const btn = document.querySelector(".o_control_panel .btn-primary");
                const label = brightness(getComputedStyle(btn).color);
                const fill = brightness(getComputedStyle(btn).backgroundColor);
                if (Math.abs(label - fill) < 90) {
                    throw new Error(
                        `button label does not contrast with its fill: ${label} vs ${fill}`
                    );
                }
                // and the fill has to stand off the page behind it
                if (Math.abs(fill - brightness(bg)) < 60) {
                    throw new Error(`the primary button vanishes into the page: ${fill}`);
                }
                // the primary colour used as *text* has to lighten too, or an
                // outline button prints #4f46e5 on a near-black background
                const link = getComputedStyle(document.documentElement)
                    .getPropertyValue("--om-theme-link");
                const probe = document.createElement("span");
                probe.style.color = link;
                document.body.appendChild(probe);
                const resolved = getComputedStyle(probe).color;
                probe.remove();
                if (brightness(resolved) < 130) {
                    throw new Error(`the link colour did not lighten for dark mode: ${resolved}`);
                }
            },
        },
    ],
});

registry.category("web_tour.tours").add("om_theme_light_tour", {
    steps: () => [
        {
            content: "the light bundle is served by default",
            trigger: ".o_web_client",
            run() {
                const bg = getComputedStyle(document.body).backgroundColor;
                if (brightness(bg) < 200) {
                    throw new Error(`body should be light: ${bg}`);
                }
            },
        },
    ],
});

registry.category("web_tour.tours").add("om_theme_toggle_tour", {
    steps: () => [
        {
            content: "the switch lives in the user menu, beside My Preferences",
            trigger: ".o_user_menu",
            run: "click",
        },
        {
            trigger: ".dropdown-menu [data-menu='preferences']",
        },
        {
            content: "and it is the next entry down",
            trigger: ".dropdown-menu [data-menu='om_color_scheme']",
            run: "click",
        },
    ],
});
