import { Component, proxy } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class CustomizerSystray extends Component {
    static template = "om_pen.CustomizerSystray";

    setup() {
        this.customizer = useService("om_pen");
        this.state = proxy(this.customizer.state);
    }
}
