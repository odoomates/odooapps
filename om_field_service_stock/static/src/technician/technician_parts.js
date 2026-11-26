import { proxy } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { FieldServiceTechnician } from "@om_field_service/technician/technician";

patch(FieldServiceTechnician.prototype, {
    setup() {
        super.setup(...arguments);
        this.parts = proxy({
            adding: false,
            query: "",
            products: [],
            product: null,
            lots: [],
            lotId: "",
            quantity: 1,
        });
    },

    async openPartForm() {
        Object.assign(this.parts, { adding: true, query: "", product: null, lots: [], lotId: "", quantity: 1 });
        await this.searchParts();
    },

    closePartForm() {
        this.parts.adding = false;
    },

    async searchParts(ev) {
        if (ev) {
            this.parts.query = ev.target.value;
        }
        this.parts.products = await this.orm.call("project.task", "fs_mobile_part_products", [
            [this.state.job.id],
            this.parts.query,
        ]);
    },

    async selectPart(product) {
        this.parts.product = product;
        this.parts.quantity = 1;
        this.parts.lotId = "";
        this.parts.lots =
            product.tracking
                ? await this.orm.call("project.task", "fs_mobile_part_lots", [[this.state.job.id], product.id])
                : [];
        if (this.parts.lots.length === 1) {
            this.parts.lotId = String(this.parts.lots[0].id);
        }
    },

    async addPart() {
        const product = this.parts.product;
        if (!product) {
            return;
        }
        await this.run(async () => {
            this.setJob(
                await this.orm.call("project.task", "fs_mobile_add_part", [
                    [this.state.job.id],
                    product.id,
                    parseFloat(this.parts.quantity) || 1,
                    Number(this.parts.lotId) || false,
                ])
            );
            this.parts.adding = false;
        });
    },

    async removePart(part) {
        await this.run(async () => {
            this.setJob(await this.orm.call("project.task", "fs_mobile_remove_part", [[this.state.job.id], part.id]));
        });
    },
});
