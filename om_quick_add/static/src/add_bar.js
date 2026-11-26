import { Component, proxy, signal, useProps } from "@odoo/owl";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { formatFloat } from "@web/views/fields/formatters";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

/**
 * The add bar, above the lines of a document: type a name or a code with a quantity and Enter, paste rows,
 * or scan into it. Empty, it lists the usual products of the partner.
 */
export class QuickAddBar extends Component {
    static template = "om_quick_add.AddBar";
    props = useProps({ ...standardWidgetProps });
    inputRef = signal.ref();

    setup() {
        this.orm = useService("orm");
        this.state = proxy({
            query: "",
            open: false,
            results: [],
            resultsFor: null,
            parsed: { quantity: 1, price: null },
            active: 0,
            pending: [],
            flash: null,
            usualOpen: false,
            data: null,
        });
        this.searchSeq = 0;
        this.lastProduct = null;
        this.debouncedSearch = useDebounced((query) => this.runSearch(query), 200);
        useHotkey("alt+shift+a", () => this.inputRef()?.focus(), { bypassEditableProtection: true });
    }

    get record() {
        return this.props.record;
    }

    get visible() {
        return !this.props.readonly && this.record.data.om_quick_add_ok;
    }

    get items() {
        if (this.state.query.trim()) {
            return this.state.resultsFor === this.state.query ? this.state.results : [];
        }
        return this.state.data?.usual || [];
    }

    get parsedLabel() {
        const { quantity, price } = this.state.parsed;
        if (!this.state.query.trim() || (quantity === 1 && price === null)) {
            return "";
        }
        let label = _t("Quantity %s", formatFloat(quantity, { digits: [16, 2] }));
        if (price !== null && price !== undefined) {
            label += " · " + _t("price %s", formatFloat(price, { digits: [16, 2] }));
        }
        return label;
    }

    info(product) {
        const parts = [];
        if (product.code) {
            parts.push(product.code);
        }
        if (product.price !== null && product.price !== undefined) {
            parts.push(formatFloat(product.price, { digits: [16, 2] }));
        }
        const history = this.state.data?.history?.[product.id];
        if (history) {
            let last = _t("last %s", formatFloat(history.last_quantity, { digits: [16, 2] }));
            if (history.last_price !== null && history.last_price !== undefined && this.state.data.has_prices) {
                last += " @ " + formatFloat(history.last_price, { digits: [16, 2] });
            }
            parts.push(last + " · " + history.count + "×");
        }
        if (product.on_hand !== undefined) {
            parts.push(_t("on hand %s", formatFloat(product.on_hand, { digits: [16, 2] })));
        }
        return parts.join("  ·  ");
    }

    // ------------------------------------------------------------------
    // Server
    // ------------------------------------------------------------------

    async ensureSaved() {
        const record = this.record;
        if (record.isNew || (await record.isDirty())) {
            return await record.save();
        }
        return true;
    }

    async call(method, args = []) {
        if (!(await this.ensureSaved())) {
            this.showFlash({ type: "warning", message: _t("Fill in the document first: it is saved before adding.") });
            return null;
        }
        return this.orm.call(this.record.resModel, method, [[this.record.resId], ...args]);
    }

    async loadData() {
        if (this.record.isNew) {
            return;
        }
        this.state.data = await this.orm.call(this.record.resModel, "om_quick_add_bar_data", [[this.record.resId]]);
    }

    async runSearch(query) {
        const seq = ++this.searchSeq;
        const result = await this.call("om_quick_add_bar_search", [query]);
        if (!result || seq !== this.searchSeq) {
            return;
        }
        this.state.results = result.products;
        this.state.parsed = { quantity: result.quantity, price: result.price };
        this.state.resultsFor = query;
        this.state.active = 0;
    }

    async afterAdd(result, product = null) {
        if (!result) {
            return;
        }
        this.showFlash(result);
        if (result.type === "success") {
            if (product || result.product_id) {
                this.lastProduct = product || { id: result.product_id };
            }
            this.state.query = "";
            this.state.results = [];
            this.state.resultsFor = null;
            this.state.parsed = { quantity: 1, price: null };
            await this.record.load();
        }
        // the list stays closed after an add, so the lines and the rows to choose are seen; typing or the
        // arrow down opens it again
        this.state.open = false;
        const input = this.inputRef();
        if (input && document.activeElement !== input) {
            this.skipOpen = true;
            input.focus();
        }
    }

    showFlash(result) {
        this.state.flash = { type: result.type, message: result.message };
        clearTimeout(this.flashTimeout);
        this.flashTimeout = setTimeout(() => (this.state.flash = null), 4000);
    }

    // ------------------------------------------------------------------
    // Adding
    // ------------------------------------------------------------------

    async addProduct(product) {
        let quantity = this.state.parsed.quantity;
        let price = this.state.parsed.price;
        if (!this.state.query.trim()) {
            // from the usual products: the last quantity of the partner
            quantity = this.state.data?.history?.[product.id]?.last_quantity || 1;
            price = null;
        }
        const result = await this.call("om_quick_add_bar_add", [product.id, quantity, price]);
        await this.afterAdd(result, product);
    }

    async enter(query) {
        if (!query.trim()) {
            return;
        }
        const result = await this.call("om_quick_add_bar_enter", [query]);
        if (result && result.choices) {
            this.state.pending.unshift({
                row: query.trim(),
                quantity: result.quantity,
                price: result.price,
                choices: result.choices,
            });
            this.state.query = "";
            this.state.resultsFor = null;
            return;
        }
        await this.afterAdd(result);
    }

    async choose(item, productId) {
        const result = await this.call("om_quick_add_bar_add", [productId, item.quantity, item.price]);
        if (result && result.type === "success") {
            this.state.pending = this.state.pending.filter((pending) => pending !== item);
        }
        await this.afterAdd(result);
    }

    onChoose(item, ev) {
        const productId = parseInt(ev.target.value, 10);
        if (productId) {
            this.choose(item, productId);
        }
    }

    closeUsualLater() {
        setTimeout(() => (this.state.usualOpen = false), 200);
    }

    dismiss(item) {
        this.state.pending = this.state.pending.filter((pending) => pending !== item);
    }

    async addUsual(mode) {
        this.state.usualOpen = false;
        const result = await this.call("om_quick_add_bar_usual", [mode]);
        await this.afterAdd(result);
    }

    // ------------------------------------------------------------------
    // Events
    // ------------------------------------------------------------------

    async onFocus() {
        if (this.skipOpen) {
            this.skipOpen = false;
        } else {
            this.state.open = true;
        }
        if (await this.ensureSaved()) {
            if (!this.state.data) {
                await this.loadData();
            }
        }
    }

    onBlur() {
        this.state.open = false;
    }

    onInput(ev) {
        this.state.query = ev.target.value;
        this.state.active = 0;
        this.state.open = true;
        if (this.state.query.trim()) {
            this.debouncedSearch(this.state.query);
        } else {
            this.state.results = [];
            this.state.resultsFor = null;
            this.state.parsed = { quantity: 1, price: null };
        }
    }

    onKeydown(ev) {
        const items = this.items;
        switch (ev.key) {
            case "ArrowDown":
                ev.preventDefault();
                if (!this.state.open) {
                    this.state.open = true;
                    break;
                }
                this.state.active = Math.min(this.state.active + 1, items.length - 1);
                break;
            case "ArrowUp":
                ev.preventDefault();
                this.state.active = Math.max(this.state.active - 1, 0);
                break;
            case "Enter": {
                ev.preventDefault();
                ev.stopPropagation();
                const query = ev.target.value;
                // the list shown is the one of what is typed: add the product picked; a scan or a code
                // typed faster than the search is resolved by the server
                if (this.state.open && items.length && (!query.trim() || this.state.resultsFor === query)) {
                    this.addProduct(items[this.state.active] || items[0]);
                } else {
                    this.enter(query);
                }
                break;
            }
            case "Escape":
                if (this.state.query) {
                    ev.preventDefault();
                    ev.stopPropagation();
                    this.state.query = "";
                    this.state.resultsFor = null;
                }
                this.state.open = false;
                break;
            case "+":
                if (!this.state.query && this.lastProduct) {
                    ev.preventDefault();
                    this.call("om_quick_add_bar_add", [this.lastProduct.id, 1, null]).then((result) =>
                        this.afterAdd(result, this.lastProduct)
                    );
                }
                break;
        }
    }

    async onPaste(ev) {
        const text = ev.clipboardData?.getData("text") || "";
        if (!text.includes("\n")) {
            return;
        }
        ev.preventDefault();
        const result = await this.call("om_quick_add_bar_paste", [text]);
        if (!result) {
            return;
        }
        this.state.pending.push(...result.pending);
        await this.afterAdd(result);
    }
}

registry.category("view_widgets").add("om_quick_add_bar", { component: QuickAddBar });
