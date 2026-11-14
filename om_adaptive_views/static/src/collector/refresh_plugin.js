import { BusPlugin } from "@bus/services/bus_plugin";
import { rpcBus } from "@web/core/network/rpc";
import { services } from "@web/core/services";

import { onWillDestroy, Plugin, usePlugin } from "@odoo/owl";

/**
 * A change applied or undone, by anyone: drop the views this browser holds, so the next
 * screen opened is built with the change.
 */
export class AdaptiveRefreshPlugin extends Plugin {
    bus = usePlugin(BusPlugin);

    setup() {
        const unsubscribe = this.bus.subscribe("om_adaptive_views/refresh", () => {
            rpcBus.trigger("CLEAR-CACHES", "get_views");
        });
        this.bus.start();
        onWillDestroy(unsubscribe);
    }
}

services.add(AdaptiveRefreshPlugin);
