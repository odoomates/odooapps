/** @odoo-module **/
// The record filters of a profile: Odoo 16's domain editor cannot show a
// filter reading the user or the date (uid, user.property_warehouse_id,
// context_today()), the ones the presets write. Such a filter is edited as text.
import { Domain } from "@web/core/domain";
import { registry } from "@web/core/registry";
import { DomainField } from "@web/views/fields/domain/domain_field";

export class AccessDomainField extends DomainField {
    get hasExpressions() {
        try {
            new Domain(this.props.value || "[]").toList();
            return false;
        } catch {
            return true;
        }
    }

    onTextChange(ev) {
        return this.props.update(ev.target.value.trim() || false);
    }
}
AccessDomainField.template = "om_access_manager.AccessDomainField";

registry.category("fields").add("om_access_domain", AccessDomainField);
