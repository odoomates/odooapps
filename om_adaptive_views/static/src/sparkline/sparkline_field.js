import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

import { Component, useProps } from "@odoo/owl";

const WIDTH = 78;
const HEIGHT = 18;

/**
 * Weekly uses as a row of small bars, oldest week on the left, from a JSON list of counts.
 */
export class SparklineField extends Component {
    static template = "om_adaptive_views.SparklineField";
    props = useProps({ ...standardFieldProps });

    get values() {
        try {
            const values = JSON.parse(this.props.record.data[this.props.name] || "[]");
            return Array.isArray(values) ? values.map((v) => Number(v) || 0) : [];
        } catch {
            return [];
        }
    }

    get bars() {
        const values = this.values;
        const max = Math.max(1, ...values);
        const step = values.length ? WIDTH / values.length : WIDTH;
        return values.map((value, index) => {
            const height = value ? Math.max(2, Math.round((value / max) * HEIGHT)) : 1;
            return { x: index * step + 1, y: HEIGHT - height, width: Math.max(1, step - 2), height, value };
        });
    }

    get title() {
        const total = this.values.reduce((sum, value) => sum + value, 0);
        return _t("%(total)s uses in the last %(weeks)s weeks", { total, weeks: this.values.length });
    }

    get width() {
        return WIDTH;
    }

    get height() {
        return HEIGHT;
    }
}

registry.category("fields").add("om_sparkline", {
    component: SparklineField,
    displayName: _t("Weekly bars"),
    supportedTypes: ["char"],
});
