import { patch } from "@web/core/utils/patch";
import { View } from "@web/views/view";
import { viewService } from "@web/views/view_service";
import { customizerState, setCustomizeActive } from "./customizer_state";

/**
 * While customize mode is on, views are loaded with the unpublished changes applied,
 * so whatever is dropped or changed shows at once. The server only honours this for
 * people who may customize, and caches it apart from the live views.
 *
 * An option rather than a context key: the view service passes options through to
 * get_views, but filters the context down to the language and *_view_ref keys.
 */
patch(viewService, {
    start(env, deps) {
        const service = super.start(env, deps);
        const loadViews = service.loadViews;
        service.loadViews = (params, options = {}) =>
            loadViews(params, customizerState.active ? { ...options, om_pen_draft: true } : options);
        return service;
    },
});

/**
 * Publish the view being displayed into the customizer state.
 *
 * `env.config` is a child sub-env created by View (view.js:228), so neither a service
 * nor a main component at the webclient root can read it. loadView is where View fills
 * it in (view.js:362), which makes it the one place that sees every view load.
 */
patch(View.prototype, {
    async loadView(props) {
        await super.loadView(props);
        const { viewId, viewType, viewArch } = this.env.config;
        customizerState.current = { resModel: props.resModel, viewId, viewType, viewArch };

        // navigating away from the customized view leaves the panel describing a view
        // that is no longer on screen, so switch the mode off
        if (customizerState.active && customizerState.config?.viewId !== viewId) {
            setCustomizeActive(false);
        }
    },
});
