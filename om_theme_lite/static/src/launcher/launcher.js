import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { normalize } from "@web/core/l10n/utils/normalize";
import { fuzzyTest } from "@web/core/utils/search";
import { useSortable } from "@web/core/utils/sortable_owl";
import { user } from "@web/core/user";
import { session } from "@web/session";

import { Component, onMounted, onPatched, onWillUnmount, signal, t, useProps } from "@odoo/owl";

/**
 * Leave no app selected, in the menu service or in session storage.
 *
 * setCurrentMenu writes the string "null" to session storage, and the webclient
 * reads that back as a number on the next boot, so the key is removed instead.
 */
export function clearCurrentApp(menuService) {
    menuService.setCurrentMenu({ appID: null });
    try {
        browser.sessionStorage.removeItem("menu_id");
    } catch {
        // storage is a convenience; losing it must not break the home screen
    }
}

// how well a name matches the search, lower is better
const EXACT = 0;
const PREFIX = 1;
const WORD = 2;
const INSIDE = 3;
const FUZZY = 4;
const MISS = Infinity;

/**
 * Score a name against the search.
 *
 * Both sides are normalised, so "facturacion" finds "Facturación". Fuzzy matching is
 * kept for app names, where it rescues a typo, and left out for menu items, where
 * it would bury the real hits under dozens of loose ones.
 */
export function matchScore(name, needle, { fuzzy = false } = {}) {
    const hay = normalize(name);
    if (hay === needle) {
        return EXACT;
    }
    if (hay.startsWith(needle)) {
        return PREFIX;
    }
    const at = hay.indexOf(needle);
    if (at > 0) {
        return /[\s/(\-_.]/.test(hay[at - 1]) ? WORD : INSIDE;
    }
    if (fuzzy && needle.length >= 3 && fuzzyTest(needle, hay)) {
        return FUZZY;
    }
    return MISS;
}

/** Split a name around the first match, for highlighting. */
export function highlightParts(name, query) {
    const at = query ? name.toLowerCase().indexOf(query.toLowerCase()) : -1;
    if (at < 0) {
        return [{ text: name, hit: false }];
    }
    return [
        { text: name.slice(0, at), hit: false },
        { text: name.slice(at, at + query.length), hit: true },
        { text: name.slice(at + query.length), hit: false },
    ].filter((part) => part.text);
}

/**
 * The app launcher.
 *
 * It needs no server data of its own: the menu service already holds every app, its
 * icon and its whole submenu tree. The one thing it keeps per user is the order of
 * the tiles, which the user sets by dragging them.
 *
 * Odoo 20 ships a new OWL - there is no `useState` anywhere in the web module - so
 * local state is a signal and props are declared with `useProps`.
 */
export class AppLauncher extends Component {
    static template = "om_theme_lite.AppLauncher";
    // OWL 3 has no useRef: a ref is a signal held as a class field and named by
    // expression in the template (t-ref="this.searchRef")
    searchRef = signal.ref();
    gridRef = signal.ref();
    // t-model binds to a signal, so the query cannot just be a proxy property
    query = signal("", { type: t.string() });
    // the result picked with the arrow keys, tied to the query it was picked for:
    // typing again starts over from the best match
    picked = signal({ query: "", index: -1 });
    // app xmlids in the order the user dragged them into
    appOrder = signal(Array.isArray(session.om_app_order) ? session.om_app_order : []);
    props = useProps({
        ...standardActionServiceProps,
    });

    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");
        this.orm = useService("orm");

        // The search box stays out of the way until there is something to search
        // for, so the first keystroke has to be caught on the document: there is
        // nothing focused to receive it.
        onMounted(() => {
            this.clearCurrentApp();
            document.addEventListener("keydown", this.onDocumentKeydown);
        });
        onWillUnmount(() => document.removeEventListener("keydown", this.onDocumentKeydown));

        // The box cannot take focus until it is on screen, and it only goes on
        // screen once the query is set - so the focus has to happen after the patch,
        // not in the handler that set it. onPatched is that moment.
        onPatched(() => {
            const input = this.searchRef();
            if (this.query() && input && document.activeElement !== input) {
                input.focus();
            }
            this.gridRef()?.querySelector(".om-active")?.scrollIntoView({ block: "nearest" });
        });

        // Tiles are reordered by dragging. Only the plain grid can be sorted: a
        // filtered list has gaps in it, so a drop there has no clear meaning.
        useSortable({
            ref: this.gridRef,
            elements: ".om-app-wrap",
            enable: () => !this.query(),
            delay: 120,
            touchDelay: 400,
            cursor: "grabbing",
            placeholderClasses: ["om-app-placeholder"],
            onDragStart: () => {
                this.dragging = true;
            },
            onDrop: ({ element, previous }) => this.onTileDrop(element, previous),
            onDragEnd: () => {
                // the pointerup that ends a drag would otherwise click the tile
                browser.setTimeout(() => (this.dragging = false));
            },
        });
    }

    /**
     * Forget which app the user came from.
     *
     * The navbar draws its brand and its menu sections from the menu service's
     * current app. Coming back here from Sales left the Sales menus sitting in the
     * navbar, which is wrong: nothing is open on the home screen, so nothing should
     * be advertised in the navbar either.
     */
    clearCurrentApp() {
        clearCurrentApp(this.menuService);
    }

    /**
     * Type anywhere on the home screen and it goes into the search box; the arrow
     * keys walk the tiles.
     *
     * This does not stop once the box is showing. If focus has not landed on the
     * input for any reason, typing would otherwise go nowhere and the search would
     * look stuck on its first character.
     */
    onDocumentKeydown = (ev) => {
        if (ev.ctrlKey || ev.metaKey || ev.altKey) {
            return; // shortcuts are not someone starting a search
        }
        if (document.querySelector(".modal, .o_dialog")) {
            return; // a dialog is open over the home screen and owns the keyboard
        }
        const input = this.searchRef();
        if (input && document.activeElement === input) {
            return; // the box has focus and handles its own typing
        }
        const target = ev.target;
        if (target instanceof Element && target.closest("input, textarea, select, [contenteditable='true']")) {
            return; // someone is typing in a field of their own
        }
        if (!this.query() && ev.key.startsWith("Arrow")) {
            ev.preventDefault();
            this.moveInGrid(ev.key);
            return;
        }
        const control = target instanceof Element && target.closest("button, a");
        if (control && [" ", "Enter"].includes(ev.key)) {
            // Space and Enter press the focused tile, they do not search. A link
            // answers Enter on its own but not Space, so Space is passed on to it.
            if (ev.key === " " && control.tagName === "A") {
                ev.preventDefault();
                control.click();
            }
            return;
        }
        if (ev.key === "Backspace") {
            ev.preventDefault();
            this.query.set(this.query().slice(0, -1));
            return;
        }
        if (ev.key.length !== 1) {
            return; // Tab and the rest are not search input
        }
        ev.preventDefault();
        this.query.set(this.query() + ev.key);
    };

    /**
     * Move focus between tiles with the arrow keys.
     *
     * Focus moves to the tile itself, so Enter and Space then open it the way they
     * open any button. Up and down jump a whole row, however many columns the
     * screen has room for.
     */
    moveInGrid(key) {
        const tiles = [...(this.gridRef()?.querySelectorAll(".om-app") || [])];
        if (!tiles.length) {
            return;
        }
        const current = tiles.indexOf(document.activeElement);
        if (current < 0) {
            tiles[0].focus();
            return;
        }
        const columns = tiles.filter((tile) => tile.offsetTop === tiles[0].offsetTop).length;
        const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -columns, ArrowDown: columns }[key];
        const next = current + step;
        if (next >= 0 && next < tiles.length) {
            tiles[next].focus();
        }
    }

    // ------------------------------------------------------------------
    // data
    // ------------------------------------------------------------------

    appKey(app) {
        return app.xmlid || String(app.id);
    }

    /** The apps, in the order the user dragged them into; new apps go last. */
    get apps() {
        const apps = this.menuService.getApps();
        const rank = new Map(this.appOrder().map((key, index) => [key, index]));
        return apps
            .map((app, index) => ({ app, index }))
            .sort((a, b) => {
                const ra = rank.get(this.appKey(a.app)) ?? rank.size + a.index;
                const rb = rank.get(this.appKey(b.app)) ?? rank.size + b.index;
                return ra - rb;
            })
            .map(({ app }) => app);
    }

    /**
     * Apps matching the search, best match first, each with the menu items that
     * matched.
     *
     * Searching only app names would miss the thing people actually look for, which
     * is a menu item buried inside an app. Every app tile and menu item is also
     * numbered in the order it is drawn, so the arrow keys can walk them.
     */
    get results() {
        const query = this.query().trim();
        const needle = normalize(query);
        let entries;
        if (!needle) {
            entries = this.apps.map((app) => ({ app, score: EXACT, items: [] }));
        } else {
            entries = this.apps
                .map((app, order) => {
                    const score = matchScore(app.name, needle, { fuzzy: true });
                    const items = this.matchingItems(app, needle);
                    // an app's own name beats a menu item that matches as well, so
                    // "sal" puts Sales ahead of CRM's "Sales Teams"
                    const best = Math.min(score, (items[0]?.score ?? MISS) + 0.5);
                    return { app, score, items, best, order };
                })
                .filter((entry) => entry.best !== MISS)
                .sort((a, b) => a.best - b.best || a.order - b.order);
            // one app left: show everything it matched, not just the first few
            const cap = entries.length === 1 ? 25 : 5;
            for (const entry of entries) {
                entry.items = entry.items.slice(0, cap);
            }
        }
        let index = 0;
        for (const entry of entries) {
            entry.index = index++;
            entry.nameParts = highlightParts(entry.app.name, query);
            for (const item of entry.items) {
                item.index = index++;
                item.nameParts = highlightParts(item.name, query);
            }
        }
        return entries;
    }

    /** Flatten an app's menu tree and keep the items whose name matches, best first. */
    matchingItems(app, needle) {
        const found = [];
        const walk = (menu, trail) => {
            for (const child of menu.childrenTree || []) {
                const path = [...trail, child.name];
                const score = child.actionID ? matchScore(child.name, needle) : MISS;
                if (score !== MISS) {
                    found.push({ id: child.id, name: child.name, path: path.join(" / "), score });
                }
                walk(child, path);
            }
        };
        walk(this.menuService.getMenuAsTree(app.id), []);
        return found.sort((a, b) => a.score - b.score);
    }

    /**
     * The result Enter opens: the one picked with the arrow keys, or else the best
     * match - the app itself when its name matches at least as well as any of its
     * menu items, so typing "Inventory" opens Inventory and not one of its menus.
     */
    get activeIndex() {
        const picked = this.picked();
        if (picked.query === this.query() && picked.index >= 0) {
            return picked.index;
        }
        const first = this.results[0];
        if (!first || !this.query().trim()) {
            return -1;
        }
        return first.items.length && first.items[0].score < first.score
            ? first.items[0].index
            : first.index;
    }

    get resultCount() {
        return this.results.reduce((count, entry) => count + 1 + entry.items.length, 0);
    }

    /** The colour, background and class of an app that has a font icon and no image. */
    fontIcon(app) {
        const raw = app.webIcon;
        if (!raw) {
            return null;
        }
        const [icon, color, backgroundColor] =
            typeof raw === "string" ? raw.split(",") : [raw.icon, raw.color, raw.backgroundColor];
        if (!icon) {
            return null;
        }
        return {
            className: icon.includes(" ") ? icon : `fa ${icon}`,
            style: `color: ${color || "#fff"}; background-color: ${backgroundColor || "var(--om-theme-primary)"};`,
        };
    }

    /** The company's background picture, set in Settings, if it has one. */
    get backgroundStyle() {
        const url = session.om_home_background;
        return url ? `--om-launcher-bg: url('${url}');` : "";
    }

    /** The address of a menu, the same one Odoo's own menus link to. */
    menuHref(menu) {
        if (!menu?.actionID) {
            return "/odoo";
        }
        return `/odoo/${menu.actionPath || "action-" + menu.actionID}`;
    }

    // ------------------------------------------------------------------
    // actions
    // ------------------------------------------------------------------

    /**
     * Tiles and menu items are real links, so the browser's own gestures work on
     * them: middle-click, Ctrl or Cmd + click and Shift + click open the menu in a
     * new tab or window. A plain click stays in the page.
     */
    onLinkClick(ev, open) {
        if (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button !== 0) {
            return;
        }
        ev.preventDefault();
        open();
    }

    openApp(app) {
        if (this.dragging) {
            return;
        }
        this.menuService.selectMenu(app);
    }

    openMenu(menuId) {
        const menu = this.menuService.getMenu(menuId);
        if (menu) {
            this.menuService.selectMenu(menu);
        }
    }

    openIndex(index) {
        for (const entry of this.results) {
            if (entry.index === index) {
                return this.openApp(entry.app);
            }
            const item = entry.items.find((candidate) => candidate.index === index);
            if (item) {
                return this.openMenu(item.id);
            }
        }
    }

    onSearchKeydown(ev) {
        if (ev.key === "Escape") {
            this.query.set("");
            return;
        }
        if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
            ev.preventDefault();
            const count = this.resultCount;
            if (!count) {
                return;
            }
            const current = this.activeIndex;
            const next = ev.key === "ArrowDown"
                ? (current + 1) % count
                : (current - 1 + count) % count;
            this.picked.set({ query: this.query(), index: next });
            return;
        }
        if (ev.key === "Enter" && this.activeIndex >= 0) {
            this.openIndex(this.activeIndex);
        }
    }

    /** Save the order the tiles were dragged into. */
    async onTileDrop(element, previous) {
        const keys = this.apps.map((app) => this.appKey(app));
        const moved = element.dataset.appKey;
        const order = keys.filter((key) => key !== moved);
        const after = previous ? order.indexOf(previous.dataset.appKey) : -1;
        order.splice(after + 1, 0, moved);
        await this.saveOrder(order);
    }

    async saveOrder(order) {
        this.appOrder.set(order);
        session.om_app_order = order;
        await this.orm.write("res.users", [user.userId], { om_app_order: order });
    }

    get emptyMessage() {
        return _t("No app or menu matches “%s”", this.query());
    }
}

registry.category("actions").add("om_theme_lite.launcher", AppLauncher);
