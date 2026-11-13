import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";
import { rpcBus } from "@web/core/network/rpc";
import { user } from "@web/core/user";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { CustomizerSystray } from "./customizer_systray";
import {
    customizerState,
    setCustomizeActive,
    setPlacing,
    CUSTOMIZABLE_VIEW_TYPES,
} from "./customizer_state";

// set before a reload that customize mode should survive
export const RESUME_KEY = "om_pen_resume";

export const customizerService = {
    dependencies: ["orm", "action", "notification", "dialog"],

    async start(env, { orm, action, notification, dialog }) {
        const allowed = await user.hasGroup("om_pen.group_customizer");
        if (allowed) {
            // registered from the service rather than at import time, so the button is
            // simply absent for a user who may not customize anything
            registry
                .category("systray")
                .add("om_pen.customizer", { Component: CustomizerSystray }, { sequence: 50 });
        }

        async function load(config) {
            const [fields, customization] = await Promise.all([
                orm.call(config.resModel, "fields_get", [], {
                    attributes: ["string", "type", "readonly", "required", "relation"],
                }),
                orm.call("om.pen.view", "get_customization", [
                    config.resModel,
                    config.viewId,
                    config.viewType,
                ]),
            ]);
            customizerState.fields = fields;
            customizerState.rules = customization.rules;
            customizerState.actions = customization.actions;
            customizerState.pages = customization.pages || [];
            customizerState.broken = Boolean(customization.broken);
            customizerState.hasDraft = Boolean(customization.has_draft);
            customizerState.draftCount = customization.draft_count || 0;
            customizerState.draftInvalid = Boolean(customization.draft_invalid);
            customizerState.subviews = await orm.call(
                "om.pen.view", "subview_targets",
                [config.resModel, config.viewId, config.viewType]
            );
        }

        const service = {
            state: customizerState,
            allowed,

            async toggle() {
                if (customizerState.active) {
                    // leaving throws away whatever is half-typed in the panel, so say so
                    if (customizerState.dirty) {
                        dialog.add(ConfirmationDialog, {
                            title: _t("Unsaved changes"),
                            body: _t(
                                "The field you are editing has changes that have not been"
                                + " applied. Leaving customize mode discards them."
                            ),
                            confirmLabel: _t("Discard and leave"),
                            confirmClass: "btn-danger",
                            confirm: () => this.leave(),
                            cancel: () => {},
                        });
                        return;
                    }
                    await this.leave();
                    return;
                }
                const current = customizerState.current;
                if (!current || !CUSTOMIZABLE_VIEW_TYPES.includes(current.viewType)) {
                    notification.add(
                        _t("Open a form or a list view first: those are the views that can be customized."),
                        { type: "warning" }
                    );
                    return;
                }
                // switch the mode on before loading: the RPCs take a moment, and a
                // click or a drag in that window used to be silently swallowed
                customizerState.config = current;
                customizerState.rules = {};
                customizerState.pages = [];
                customizerState.subviews = [];
                setCustomizeActive(true);
                await load(current);
                if (customizerState.hasDraft) {
                    // the screen still shows the live view: show the draft instead
                    await this.refresh();
                }
            },

            /** Leave customize mode, and back to the live view if a draft was on screen. */
            async leave() {
                const showedDraft = customizerState.hasDraft;
                setCustomizeActive(false);
                if (showedDraft) {
                    rpcBus.trigger("CLEAR-CACHES", "get_views");
                    await action.doAction("soft_reload");
                }
            },

            /**
             * Edit another field, or none. Switching away from unapplied edits would
             * throw them away without a word, so it asks first, as leaving does.
             */
            select(fieldName, shownLabel = "") {
                const go = () => {
                    customizerState.shownLabel = shownLabel;
                    customizerState.selected = fieldName;
                };
                if (!customizerState.dirty || fieldName === customizerState.selected) {
                    go();
                    return;
                }
                dialog.add(ConfirmationDialog, {
                    title: _t("Unsaved changes"),
                    body: _t(
                        "The field you are editing has changes that have not been"
                        + " applied. Switching to another field discards them."
                    ),
                    confirmLabel: _t("Discard and switch"),
                    confirmClass: "btn-danger",
                    confirm: go,
                    cancel: () => {},
                });
            },

            /** Hold a field aside until the user clicks where it should go. */
            startAdding(fieldName) {
                customizerState.selected = null;
                customizerState.adding = fieldName;
                setPlacing(true);
            },

            cancelAdding() {
                customizerState.adding = null;
                setPlacing(false);
            },

            async moveField(fieldName, anchorField, position, pageName = null) {
                await this._call("move_field_rule", [
                    fieldName, anchorField, position, pageName,
                ]);
            },

            /** Make the pending changes the ones everybody sees. */
            async publish() {
                await this._call("publish", []);
            },

            async discardDraft() {
                return new Promise((resolve) => {
                    dialog.add(ConfirmationDialog, {
                        title: _t("Discard unpublished changes"),
                        body: _t(
                            "Everything that has not been published on this view will be"
                            + " thrown away. What is already live stays as it is."
                        ),
                        confirmLabel: _t("Discard them"),
                        confirmClass: "btn-danger",
                        confirm: async () => {
                            await this._call("discard_draft", []);
                            resolve();
                        },
                        cancel: () => resolve(),
                    });
                });
            },

            async addSubviewField(subField, subViewType, fieldName) {
                await this._call("add_subview_field_rule", [
                    subField, subViewType, fieldName,
                ]);
            },

            async placeField(
                anchorField,
                { pageId = null, pageName = null, position = null, schemaChanged = false } = {}
            ) {
                const fieldName = customizerState.adding;
                const { resModel, viewId, viewType } = customizerState.config;
                // saving until the view is reloaded too: publishing in between would
                // race the reload and could leave the old view on screen
                customizerState.saving = true;
                try {
                    await orm.call("om.pen.view", "add_field_rule", [
                        resModel,
                        viewId,
                        viewType,
                        fieldName,
                        anchorField,
                        position || customizerState.placement,
                        pageId,
                        pageName,
                    ]);
                } catch (error) {
                    customizerState.saving = false;
                    throw error;
                }
                customizerState.adding = null;
                setPlacing(false);
                if (schemaChanged) {
                    // a new field changes the model itself, and parts of the web client
                    // keep the old field list until the page is loaded again; a list
                    // then meets a column it has no field for. Reload once and come
                    // straight back to customize mode with the new field picked.
                    browser.sessionStorage.setItem(
                        RESUME_KEY,
                        JSON.stringify({ viewId: customizerState.config.viewId, selected: fieldName })
                    );
                    browser.location.reload();
                    return;
                }
                try {
                    await this.refresh();
                } finally {
                    customizerState.saving = false;
                }
                customizerState.selected = fieldName;
            },

            async saveField(fieldName, values) {
                await this._call("save_field_rule", [fieldName, values]);
            },

            async addPage(title) {
                await this._call("add_page", [title]);
            },

            async removePage(pageId) {
                await this._call("remove_page", [pageId]);
            },

            async removeField(fieldName) {
                await this._call("remove_field_rule", [fieldName]);
                customizerState.selected = null;
            },

            async saveActions(values) {
                await this._call("save_actions", [values]);
            },

            async reset() {
                const { viewId } = customizerState.config;
                customizerState.saving = true;
                try {
                    await orm.call("om.pen.view", "reset_view", [viewId]);
                } finally {
                    customizerState.saving = false;
                }
                await this.refresh();
            },

            async _call(method, extraArgs) {
                const { resModel, viewId, viewType } = customizerState.config;
                customizerState.saving = true;
                try {
                    await orm.call("om.pen.view", method, [
                        resModel,
                        viewId,
                        viewType,
                        ...extraArgs,
                    ]);
                    await this.refresh();
                } finally {
                    customizerState.saving = false;
                }
            },

            /**
             * Re-render the view that is on screen.
             *
             * view_service only busts the get_views cache when the RPC itself targets
             * ir.ui.view (view_service.js:45). Ours targets om.pen.view, so the
             * write happens server side and the client would keep serving the stale
             * arch: the cache has to be cleared by hand before reloading.
             */
            /** Reload the view; one reload at a time, so an older one never lands last. */
            refresh() {
                this._refreshing = (this._refreshing || Promise.resolve())
                    .catch(() => {})
                    .then(() => this._refresh());
                return this._refreshing;
            },

            async _refresh() {
                const config = customizerState.config;
                rpcBus.trigger("CLEAR-CACHES", "get_views");
                await load(config);
                await action.doAction("soft_reload");
                // soft_reload re-runs the View patch, which clears the mode when the
                // view id changes; it did not change here, so the mode survives
                customizerState.config = customizerState.current || config;
            },
        };
        // back from the reload that followed creating a field: wait for the same view,
        // switch customize mode on again and pick the new field
        const resume = allowed && JSON.parse(browser.sessionStorage.getItem(RESUME_KEY) || "null");
        if (resume) {
            browser.sessionStorage.removeItem(RESUME_KEY);
            let tries = 0;
            const timer = browser.setInterval(async () => {
                tries++;
                if (customizerState.current?.viewId === resume.viewId && !customizerState.active) {
                    browser.clearInterval(timer);
                    await service.toggle();
                    customizerState.selected = resume.selected;
                } else if (tries > 75) {
                    browser.clearInterval(timer);
                }
            }, 200);
        }

        return service;
    },
};

registry.category("services").add("om_pen", customizerService);
