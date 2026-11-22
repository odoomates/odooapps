import { Domain, InvalidDomainError } from "@web/core/domain";
import { EvaluationError } from "@web/core/py_js/py_builtin";
import { registry } from "@web/core/registry";
import { domainContainsExpresssions } from "@web/core/tree_editor/condition_tree";
import { user } from "@web/core/user";
import { DomainField, domainField } from "@web/views/fields/domain/domain_field";

/**
 * The user a filter is read for, in the browser: any field of it is empty, so
 * user.property_warehouse_id.id counts as no warehouse here; the server reads the real one.
 */
const EMPTY_USER = new Proxy({}, {
    get: (target, key) => (key === "id" ? false : typeof key === "symbol" ? undefined : EMPTY_USER),
});

/**
 * The record filter of a profile rule: Odoo's domain field, knowing the names the
 * server gives these filters (uid, user, company_ids). A filter on the user themselves is
 * no mistake here: no warning, and the count is the one of the current user.
 */
export class RuleDomainField extends DomainField {
    getEvaluatedDomain(props = this.props) {
        const repr = this.getDomain(props);
        if (!domainContainsExpresssions(repr)) {
            return super.getEvaluatedDomain(props);
        }
        const context = {
            ...this.getContext(props),
            uid: user.userId,
            company_ids: user.context.allowed_company_ids || [],
            user: EMPTY_USER,
        };
        try {
            return new Domain(repr).toList(context);
        } catch (error) {
            if (error instanceof InvalidDomainError || error instanceof EvaluationError) {
                return { isInvalid: true };
            }
            throw error;
        }
    }
}

registry.category("fields").add("om_rule_domain", {
    ...domainField,
    component: RuleDomainField,
    extractProps: (fieldInfo, dynamicInfo) => ({ ...domainField.extractProps(fieldInfo, dynamicInfo), allowExpressions: true }),
});
