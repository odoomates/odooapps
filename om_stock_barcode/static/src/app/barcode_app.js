import { Component, onMounted, onWillStart, onWillUnmount, proxy, signal, usePlugin, useProps } from "@odoo/owl";
import { BarcodePlugin } from "@barcodes/barcode_plugin";
import { browser } from "@web/core/browser/browser";
import { BarcodeVideoScanner, isBarcodeScannerSupported } from "@web/core/barcode/barcode_video_scanner";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { signalScan, unlockAudio } from "./feedback";

const MODEL = "om.stock.barcode";
const MUTE_KEY = "om_stock_barcode.muted";

const TYPE_ICONS = {
    incoming: "arrow_downward",
    outgoing: "local_shipping",
    internal: "swap_horiz",
};

/**
 * The Barcode app: one client action with a few screens (home, transfers of
 * an operation type, a transfer, inventory count, lookup). Each scan goes to
 * the server, which checks and applies it and sends back the screen data.
 */
export class StockBarcodeApp extends Component {
    static template = "om_stock_barcode.App";
    static components = { BarcodeVideoScanner };

    props = useProps(standardActionServiceProps);
    manualRef = signal.ref();
    qtyRef = signal.ref();

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.barcode = usePlugin(BarcodePlugin);
        this.typeIcons = TYPE_ICONS;
        this.cameraSupported = isBarcodeScannerSupported();
        this.state = proxy({
            screen: "home",
            home: null,
            list: null,
            picking: null,
            pickingState: {},
            countLocations: null,
            count: null,
            countState: {},
            lookup: null,
            feedback: null,
            flash: "",
            busy: false,
            camera: false,
            manual: "",
            search: "",
            editLine: null,
            editValue: "",
            products: null,
            muted: browser.localStorage.getItem(MUTE_KEY) === "1",
            done: null,
            lastLine: null,
        });
        this.queue = Promise.resolve();
        this.history = [];
        useBus(this.barcode.bus, "barcode_scanned", (ev) => this.scan(ev.detail.barcode));
        onWillStart(() => this.loadHome());
        onMounted(() => {
            this.unlock = () => unlockAudio();
            browser.addEventListener("pointerdown", this.unlock, { once: true });
        });
        onWillUnmount(() => {
            browser.removeEventListener("pointerdown", this.unlock);
            clearTimeout(this.flashTimer);
        });
    }

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------

    get settings() {
        return (
            this.state.picking?.settings ||
            this.state.count?.settings ||
            this.state.home?.settings ||
            {}
        );
    }

    get allTransfersLabel() {
        return _t("All transfers");
    }

    get soundOn() {
        return this.settings.sound !== false && !this.state.muted;
    }

    get cameraAllowed() {
        return this.cameraSupported && this.settings.camera !== false;
    }

    fmt(value) {
        if (value === null || value === undefined || value === "") {
            return "";
        }
        return String(Math.round(Number(value) * 1000) / 1000);
    }

    shortDate(value) {
        return value ? value.slice(0, 16) : "";
    }

    toggleMute() {
        this.state.muted = !this.state.muted;
        browser.localStorage.setItem(MUTE_KEY, this.state.muted ? "1" : "0");
    }

    show(feedback) {
        if (!feedback) {
            return;
        }
        if (feedback.message) {
            this.state.feedback = { type: feedback.type, message: feedback.message };
        }
        const kind = feedback.sound || feedback.type;
        if (["success", "error", "warning", "location", "ask", "done"].includes(kind)) {
            signalScan(kind, this.soundOn);
        }
        if (["success", "error", "warning"].includes(feedback.type) && feedback.sound !== "none") {
            this.state.flash = feedback.type;
            clearTimeout(this.flashTimer);
            this.flashTimer = setTimeout(() => (this.state.flash = ""), 700);
        }
    }

    async call(method, args) {
        this.state.busy = true;
        try {
            return await this.orm.call(MODEL, method, args);
        } finally {
            this.state.busy = false;
        }
    }

    go(screen) {
        this.history.push(this.state.screen);
        this.state.screen = screen;
        this.state.feedback = null;
        this.state.products = null;
        this.state.editLine = null;
        this.state.camera = this.state.camera && screen !== "home";
    }

    async back() {
        const previous = this.history.pop() || "home";
        this.state.feedback = null;
        this.state.products = null;
        this.state.editLine = null;
        this.state.done = null;
        if (previous === "home") {
            this.history = [];
            await this.loadHome();
        } else if (previous === "type") {
            await this.loadList(this.state.list?.picking_type?.id);
        } else if (previous === "count_list") {
            await this.loadCountLocations();
        }
        this.state.screen = previous;
    }

    async goHome() {
        this.history = [];
        this.state.feedback = null;
        this.state.done = null;
        await this.loadHome();
        this.state.screen = "home";
    }

    // ------------------------------------------------------------------
    // Scans
    // ------------------------------------------------------------------

    /** Scans are processed one after the other, as fast as they come. */
    scan(barcode) {
        barcode = (barcode || "").trim();
        if (!barcode || document.querySelector(".modal .o_dialog, .o_dialog .modal")) {
            // nothing to scan, or a dialog (backorder...) waits for an answer
            return this.queue;
        }
        this.queue = this.queue.then(() => this.processScan(barcode)).catch((error) => {
            this.show({ type: "error", message: error?.data?.message || error?.message || String(error) });
        });
        return this.queue;
    }

    async processScan(barcode) {
        const screen = this.state.screen;
        this.state.done = null;
        if (screen === "picking") {
            return this.scanPicking(barcode);
        }
        if (screen === "count") {
            return this.scanCount(barcode);
        }
        if (screen === "count_list") {
            const result = await this.call("count_open", [barcode]);
            if (result.location_id) {
                return this.openCount(result.location_id);
            }
            return this.show(result);
        }
        if (screen === "lookup") {
            return this.doLookup(barcode);
        }
        const result = await this.call("home_scan", [barcode]);
        return this.openResult(result, barcode);
    }

    async openResult(result, barcode) {
        if (result.open === "type") {
            signalScan("location", this.soundOn);
            return this.openType(result.id);
        }
        if (result.open === "picking") {
            signalScan("location", this.soundOn);
            return this.openPicking(result.id);
        }
        if (result.open === "lookup") {
            this.go("lookup");
            return this.doLookup(barcode || result.barcode);
        }
        this.show(result);
    }

    onManualKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.submitManual();
        }
    }

    onManualInput(ev) {
        this.state.manual = ev.target.value;
    }

    async submitManual() {
        const value = (this.state.manual || "").trim();
        if (!value) {
            return;
        }
        this.state.manual = "";
        if (this.manualRef()) {
            this.manualRef().value = "";
            this.manualRef().blur();
        }
        await this.scan(value);
        if (
            this.state.screen === "picking" &&
            this.state.feedback?.type === "error" &&
            this.state.picking?.rules?.unplanned !== undefined &&
            !this.state.pickingState.pending_product_id
        ) {
            // Typed text that is no barcode: offer the products it matches.
            const products = await this.call("search_products", [value]);
            this.state.products = products.length ? products : null;
        }
    }

    // ------------------------------------------------------------------
    // Camera
    // ------------------------------------------------------------------

    toggleCamera() {
        unlockAudio();
        this.state.camera = !this.state.camera;
    }

    onCameraResult(barcode) {
        this.scan(barcode);
    }

    onCameraError(error) {
        this.state.camera = false;
        this.show({ type: "error", message: error?.message || _t("The camera could not start.") });
    }

    // ------------------------------------------------------------------
    // Home and transfer lists
    // ------------------------------------------------------------------

    async loadHome() {
        this.state.home = await this.call("get_home", []);
    }

    get groupedTypes() {
        const groups = [];
        const byWarehouse = {};
        for (const type of this.state.home?.operation_types || []) {
            const key = type.warehouse || "";
            if (!byWarehouse[key]) {
                byWarehouse[key] = { name: key, types: [] };
                groups.push(byWarehouse[key]);
            }
            byWarehouse[key].types.push(type);
        }
        return groups;
    }

    async loadList(typeId, search = "") {
        this.state.list = await this.call("get_pickings", [typeId || false, search]);
    }

    async openType(typeId) {
        this.state.search = "";
        await this.loadList(typeId);
        this.go("type");
    }

    async openAllTransfers() {
        this.state.search = "";
        await this.loadList(false);
        this.go("type");
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(
            () => this.loadList(this.state.list?.picking_type?.id, this.state.search),
            300
        );
    }

    async newPicking() {
        const result = await this.call("new_picking", [this.state.list.picking_type.id]);
        return this.openPicking(result.id);
    }

    // ------------------------------------------------------------------
    // Transfer
    // ------------------------------------------------------------------

    async openPicking(pickingId) {
        this.state.pickingState = {};
        this.state.picking = await this.call("get_picking", [pickingId]);
        if (this.state.screen !== "picking") {
            this.go("picking");
        }
        this.state.feedback = null;
    }

    applyPickingResult(result) {
        if (result.state) {
            this.state.pickingState = result.state;
        }
        if (result.picking) {
            this.state.picking = result.picking;
        }
        if (result.line_id) {
            this.state.lastLine = result.line_id;
            this.scrollToLine(result.line_id);
        }
        this.show(result);
    }

    scrollToLine(lineId) {
        browser.requestAnimationFrame(() => {
            const el = document.querySelector(`.o_om_barcode_line[data-line-id="${lineId}"]`);
            el?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
        });
    }

    async scanPicking(barcode) {
        const result = await this.call("picking_scan", [
            this.state.picking.id,
            barcode,
            this.state.pickingState,
        ]);
        this.state.products = null;
        if (result.open) {
            return this.openResult(result, barcode);
        }
        this.applyPickingResult(result);
    }

    get pickingGroups() {
        const picking = this.state.picking;
        if (!picking) {
            return [];
        }
        const groups = [];
        const byKey = {};
        for (const line of picking.lines) {
            const key = line.group ? line.group.id : 0;
            if (!byKey[key]) {
                byKey[key] = { key, name: line.group ? line.group.name : "", lines: [] };
                groups.push(byKey[key]);
            }
            byKey[key].lines.push(line);
        }
        return groups;
    }

    get pickingSubtitle() {
        const picking = this.state.picking;
        return [picking.type.name, picking.partner].filter(Boolean).join(" - ");
    }

    get pickingPrompt() {
        const picking = this.state.picking;
        const pstate = this.state.pickingState;
        if (!picking) {
            return "";
        }
        if (pstate.pending_product_id) {
            return _t("Scan the lot or serial number of %(product)s", {
                product: pstate.pending_product_name,
            });
        }
        if (
            picking.rules.source &&
            picking.source_internal &&
            picking.settings.multi_location &&
            !pstate.source_location_id
        ) {
            return _t("Scan the source location");
        }
        if (picking.rules.package && picking.pending_pack) {
            return _t("Scan a package or tap Pack");
        }
        if (
            picking.rules.dest &&
            picking.dest_internal &&
            picking.settings.multi_location &&
            picking.pending_dest
        ) {
            return _t("Scan the destination location");
        }
        if (picking.lines.length && picking.lines.every((line) => line.complete)) {
            return _t("All done: validate");
        }
        return _t("Scan a product");
    }

    lineClass(line) {
        const classes = [];
        if (line.complete) {
            classes.push(line.extra ? "o_om_barcode_line_extra" : "o_om_barcode_line_done");
        } else if (line.done) {
            classes.push("o_om_barcode_line_partial");
        }
        if (this.state.lastLine === line.id) {
            classes.push("o_om_barcode_line_last");
        }
        return classes.join(" ");
    }

    async changeQty(line, delta) {
        const qty = Math.max(0, Number(line.done || 0) + delta);
        const result = await this.call("picking_set_qty", [
            this.state.picking.id,
            line.id,
            qty,
            this.state.pickingState,
        ]);
        this.applyPickingResult(result);
    }

    async fillLine(line) {
        const result = await this.call("picking_set_qty", [
            this.state.picking.id,
            line.id,
            line.demand,
            this.state.pickingState,
        ]);
        this.applyPickingResult(result);
    }

    editQty(id, value) {
        this.state.editLine = id;
        this.state.editValue = this.fmt(value);
        browser.requestAnimationFrame(() => {
            this.qtyRef()?.focus();
            this.qtyRef()?.select();
        });
    }

    onQtyInput(ev) {
        this.state.editValue = ev.target.value;
    }

    onQtyKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.saveQty();
        } else if (ev.key === "Escape") {
            this.state.editLine = null;
        }
    }

    async saveQty() {
        const id = this.state.editLine;
        if (id === null) {
            return;
        }
        const raw = (this.state.editValue || "").replace(",", ".").trim();
        this.state.editLine = null;
        if (this.state.screen === "picking") {
            const value = Number(raw);
            if (Number.isNaN(value)) {
                return this.show({ type: "error", message: _t("Enter a number.") });
            }
            const result = await this.call("picking_set_qty", [
                this.state.picking.id,
                id,
                value,
                this.state.pickingState,
            ]);
            return this.applyPickingResult(result);
        }
        if (this.state.screen === "count") {
            if (raw !== "" && Number.isNaN(Number(raw))) {
                return this.show({ type: "error", message: _t("Enter a number.") });
            }
            return this.setCount(id, raw === "" ? false : Number(raw));
        }
    }

    async addMove(move) {
        const result = await this.call("picking_add_move", [
            this.state.picking.id,
            move.move_id,
            this.state.pickingState,
        ]);
        this.applyPickingResult(result);
    }

    async addProduct(product) {
        this.state.products = null;
        const result = await this.call("picking_add_product", [
            this.state.picking.id,
            product.id,
            this.state.pickingState,
        ]);
        this.applyPickingResult(result);
    }

    clearSource() {
        const pstate = { ...this.state.pickingState };
        delete pstate.source_location_id;
        delete pstate.source_location_name;
        this.state.pickingState = pstate;
    }

    clearPending() {
        const pstate = { ...this.state.pickingState };
        delete pstate.pending_product_id;
        delete pstate.pending_product_name;
        delete pstate.pending_qty;
        this.state.pickingState = pstate;
        this.state.feedback = null;
    }

    async putInPack() {
        const result = await this.call("picking_put_in_pack", [
            this.state.picking.id,
            this.state.pickingState,
        ]);
        this.applyPickingResult(result);
    }

    async validate() {
        const pickingId = this.state.picking.id;
        const result = await this.call("picking_validate", [pickingId, this.state.pickingState]);
        if (result.action) {
            this.applyPickingResult(result);
            await this.action.doAction(result.action, {
                onClose: () => this.afterValidateWizard(pickingId),
            });
            return;
        }
        return this.pickingDone(result);
    }

    async afterValidateWizard(pickingId) {
        const result = await this.call("picking_result", [pickingId]);
        if (result.done) {
            return this.pickingDone(result);
        }
        this.applyPickingResult(result);
    }

    async pickingDone(result) {
        if (!result.done) {
            return this.applyPickingResult(result);
        }
        this.show(result);
        this.state.done = result.message;
        this.state.camera = false;
        const typeId = result.picking_type_id;
        this.history = ["home"];
        await this.loadList(typeId);
        this.state.screen = "type";
    }

    // ------------------------------------------------------------------
    // Inventory count
    // ------------------------------------------------------------------

    async loadCountLocations() {
        const result = await this.call("get_count_locations", []);
        this.state.countLocations = result.locations;
    }

    async openCountList() {
        await this.loadCountLocations();
        this.go("count_list");
    }

    async openCount(locationId) {
        this.state.countState = {};
        this.state.count = await this.call("get_count", [locationId]);
        if (this.state.screen !== "count") {
            this.go("count");
        }
    }

    applyCountResult(result) {
        if (result.state) {
            this.state.countState = result.state;
        }
        if (result.count) {
            this.state.count = result.count;
        }
        if (result.quant_id) {
            this.state.lastLine = result.quant_id;
            this.scrollToLine(result.quant_id);
        }
        this.show(result);
    }

    async scanCount(barcode) {
        const result = await this.call("count_scan", [
            this.state.count.location.id,
            barcode,
            this.state.countState,
        ]);
        this.applyCountResult(result);
    }

    async setCount(quantId, qty) {
        const result = await this.call("count_set_qty", [
            this.state.count.location.id,
            quantId,
            qty,
            this.state.countState,
        ]);
        this.applyCountResult(result);
    }

    async changeCount(line, delta) {
        const base = line.counted === null ? 0 : Number(line.counted);
        return this.setCount(line.id, Math.max(0, base + delta));
    }

    countClass(line) {
        const classes = [];
        if (line.counted !== null) {
            classes.push(line.diff ? "o_om_barcode_line_diff" : "o_om_barcode_line_done");
        }
        if (this.state.lastLine === line.id) {
            classes.push("o_om_barcode_line_last");
        }
        return classes.join(" ");
    }

    get countPrompt() {
        const cstate = this.state.countState;
        if (cstate.pending_product_id) {
            return _t("Scan the lot or serial number of %(product)s", {
                product: cstate.pending_product_name,
            });
        }
        return _t("Scan products, or a shelf or package inside this location");
    }

    clearCountContext() {
        this.state.countState = {};
        this.state.feedback = null;
    }

    async applyCount() {
        const locationId = this.state.count.location.id;
        const result = await this.call("count_apply", [locationId, this.state.countState]);
        if (result.action) {
            this.applyCountResult(result);
            await this.action.doAction(result.action, {
                onClose: () => this.openCount(locationId),
            });
            return;
        }
        this.applyCountResult(result);
    }

    // ------------------------------------------------------------------
    // Lookup
    // ------------------------------------------------------------------

    openLookup() {
        this.state.lookup = null;
        this.go("lookup");
    }

    async doLookup(barcode) {
        const result = await this.call("lookup", [barcode]);
        if (result.type === "error") {
            return this.show(result);
        }
        this.state.lookup = result;
        this.state.feedback = null;
        signalScan("success", this.soundOn);
    }
}

registry.category("actions").add("om_stock_barcode.app", StockBarcodeApp);
