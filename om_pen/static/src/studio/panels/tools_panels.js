import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { studioSections } from "../studio_action";

/** The texts of the published view and the custom fields, in every installed language. */
export class TranslationsPanel extends Component {
    static template = "om_pen.TranslationsPanel";
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({ data: null });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("om.pen.studio", "studio_translations", [
            this.props.store.info.customization_id,
        ]);
    }

    async save(row, lang, ev) {
        const value = ev.target.value;
        if ((row.values[lang] || "") === value) {
            return;
        }
        await this.orm.call("om.pen.studio", "studio_translation_save", [row.kind, row.id, lang, row.source, value]);
        row.values[lang] = value;
        this.notification.add(_t("Saved."), { type: "success" });
    }
}

/** Health check, export and import of everything made in the Studio. */
export class ToolsPanel extends Component {
    static template = "om_pen.ToolsPanel";
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({ issues: null, checking: false, exporting: false, importing: false, imported: null });
    }

    async check() {
        this.state.checking = true;
        try {
            this.state.issues = await this.orm.call("om.pen.studio", "studio_health", []);
        } finally {
            this.state.checking = false;
        }
    }

    async fix(issue) {
        const count = await this.orm.call("om.pen.studio", "studio_health_fix", [issue.id]);
        this.notification.add(_t("%s change(s) dropped from the draft. Publish the view to apply.", count), {
            type: "success",
        });
        await this.check();
    }

    async open(issue) {
        await this.props.studio.openModel({ model: issue.model, viewType: issue.view_type || "form" });
    }

    async exportAll() {
        this.state.exporting = true;
        try {
            const content = await this.orm.call("om.pen.studio", "studio_export", []);
            const bytes = Uint8Array.from(atob(content), (c) => c.charCodeAt(0));
            const url = URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
            const link = document.createElement("a");
            link.href = url;
            link.download = "om_pen_studio_export.zip";
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
        } finally {
            this.state.exporting = false;
        }
    }

    async importFile(ev) {
        const file = ev.target.files[0];
        if (!file) {
            return;
        }
        this.state.importing = true;
        try {
            const content = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result.split(",")[1]);
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });
            this.state.imported = await this.orm.call("om.pen.studio", "studio_import", [content]);
        } finally {
            this.state.importing = false;
            ev.target.value = "";
        }
    }
}

studioSections.add("translations", { label: _t("Translations"), Component: TranslationsPanel }, { sequence: 70 });
studioSections.add("tools", { label: _t("Tools"), Component: ToolsPanel, global: true }, { sequence: 80 });
