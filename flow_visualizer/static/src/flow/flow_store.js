import { proxy } from "@odoo/owl";
import { session } from "@web/session";

/**
 * Shared by the systray button and the panel: whether the visualizer is on
 * for this session, the traces read so far and how they are shown.
 */
export const flowStore = proxy({
    allowed: Boolean(session.flow_visualizer),
    enabled: Boolean(session.flow_visualizer?.enabled),
    traces: [],
    selectedId: null,
    showTechnical: false,
    view: "story",
    replay: 0,
    collapsed: {},
    // the simulator: its steps, as the server tells them
    sim: { active: Boolean(session.flow_visualizer?.simulation), steps: [] },
    simBusy: false,
});
