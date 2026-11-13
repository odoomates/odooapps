import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class CustomizerSystray extends Component {
    static template = "om_pen.CustomizerSystray";
    static props = {};

    setup() {
        this.customizer = useService("om_pen");
        this.state = useState(this.customizer.state);
    }
}
