import { Component, t, useProps } from "@odoo/owl";
import { bind } from "./customizer_state";
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
    bind = bind;
    props = useProps({
        label: t.string(),
        entry: t.object(),
        fields: t.object(),
        fieldNames: t.array(),
    });

    setMode(mode) {
        this.props.entry.mode = mode;
    }

    toggleRaw() {
        this.props.entry.cond.raw = !this.props.entry.cond.raw;
    }
}
