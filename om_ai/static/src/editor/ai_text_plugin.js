import { Plugin } from "@html_editor/plugin";
import { isHtmlContentSupported } from "@html_editor/core/selection_plugin";
import { MAIN_PLUGINS } from "@html_editor/plugin_sets";
import { withSequence } from "@html_editor/utils/resource";
import { _t } from "@web/core/l10n/translation";
import { session } from "@web/session";
import { AiTextDialog } from "./ai_text_dialog";

export class OmAiTextPlugin extends Plugin {
    static id = "omAiText";
    static dependencies = ["baseContainer", "dialog", "dom", "history", "sanitize", "selection"];
    /** @type {import("plugins").EditorResources} */
    resources = {
        user_commands: [
            {
                id: "omAiWriteText",
                title: _t("Write with AI"),
                description: _t("Generate text with your AI provider"),
                icon: "memory",
                run: this.openDialog.bind(this),
                isAvailable: (selection) => !!session.om_ai_writer && isHtmlContentSupported(selection),
            },
        ],
        powerbox_categories: withSequence(70, { id: "om_ai", name: _t("AI") }),
        powerbox_items: [
            {
                categoryId: "om_ai",
                commandId: "omAiWriteText",
            },
        ],
    };

    openDialog() {
        const selectedText = this.dependencies.selection.getEditableSelection().toString() || "";
        this.dependencies.dialog.addDialog(AiTextDialog, {
            baseContainer: this.dependencies.baseContainer.getDefaultNodeName(),
            document: this.document,
            sanitize: this.dependencies.sanitize.sanitize,
            selectedText,
            insert: (fragment) => {
                this.dependencies.dom.insert(fragment);
                this.dependencies.history.commit();
            },
        });
    }
}

MAIN_PLUGINS.push(OmAiTextPlugin);
