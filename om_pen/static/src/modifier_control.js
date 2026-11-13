import { Component } from "@odoo/owl";
import { ConditionBuilder } from "./condition_builder";

/**
 * One modifier row: Auto / Yes / No / If…, and when it is conditional, either the
 * condition builder or a hand written expression.
 *
 * This is a component rather than a t-call template because a t-call cannot host a
 * child component reliably: the branch renders, but the calling component stops
 * re-rendering on state changes inside it.
 */
export class ModifierControl extends Component {
    static template = "om_pen.ModifierControl";
    static components = { ConditionBuilder };
    static props = {
        label: { type: String },
        entry: { type: Object },
        fields: { type: Object },
        fieldNames: { type: Array },
    };

    setMode(mode) {
        this.props.entry.mode = mode;
    }

    toggleRaw() {
        this.props.entry.cond.raw = !this.props.entry.cond.raw;
    }
}
