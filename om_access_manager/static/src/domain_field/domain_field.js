/** @odoo-module **/
// The record filters of a profile: Odoo 15's domain editor cannot show a
// filter reading the user or the date (uid, user.property_warehouse_id,
// context_today()), the ones the presets write. Such a filter is edited as text.
import { _t } from "@web/core/l10n/translation";
import basicFields from "web.basic_fields";
import fieldRegistry from "web.field_registry";

/** Whether a domain reads a name (uid, user...) besides fixed values. */
function hasExpressions(value) {
    const bare = (value || "").replace(/'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"/g, "");
    return /\b(?!(?:True|False|None)\b)[A-Za-z_]\w*/.test(bare);
}

const AccessDomainField = basicFields.FieldDomain.extend({
    async _render() {
        if (!hasExpressions(this.value)) {
            if (this._omText) {
                this._omText = false;
                this.$el.empty();
                this._$content = null;
            }
            return this._super(...arguments);
        }
        this._omText = true;
        if (this.domainSelector) {
            this.domainSelector.destroy();
            this.domainSelector = null;
        }
        this._$content = null;
        this.$el.empty();
        if (this.mode === "edit") {
            $('<textarea class="o_input text-monospace w-100" rows="2"/>')
                .val(this.value)
                .on("change", (ev) => this._setValue(ev.target.value.trim() || false))
                .appendTo(this.$el);
        } else {
            $("<code/>").text(this.value).appendTo(this.$el);
        }
        $('<div class="text-muted small"/>').text(_t("It reads the user or the date: edited as text."))
            .appendTo(this.$el);
    },
});

fieldRegistry.add("om_access_domain", AccessDomainField);
