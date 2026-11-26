import { Component, markup, onWillDestroy, proxy, signal, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

/**
 * Turn plain AI text into editor blocks: lines become paragraphs, "- " lines
 * become bullet lists, "1. " lines numbered lists. Text is never parsed as HTML.
 */
export function textToFragment(text, baseContainer, document) {
    const fragment = document.createDocumentFragment();
    let list = null;
    for (const rawLine of (text || "").split("\n")) {
        const line = rawLine.trim();
        const bullet = line.match(/^[-*]\s+(.*)/);
        const number = line.match(/^\d+[.)]\s+(.*)/);
        const tag = bullet ? "UL" : number ? "OL" : null;
        if (list && list.tagName !== tag) {
            fragment.appendChild(list);
            list = null;
        }
        if (tag) {
            list = list || document.createElement(tag);
            const li = document.createElement("li");
            li.textContent = (bullet || number)[1].replace(/\*\*/g, "");
            list.appendChild(li);
        } else if (line) {
            const block = document.createElement(line.startsWith("#") ? "h3" : baseContainer);
            block.textContent = line.replace(/^#+\s*/, "").replace(/\*\*/g, "");
            fragment.appendChild(block);
        }
    }
    if (list) {
        fragment.appendChild(list);
    }
    return fragment;
}

export class AiTextDialog extends Component {
    static components = { Dialog };
    static template = "om_ai.AiTextDialog";

    props = useProps({
        baseContainer: t.string().optional("DIV"),
        close: t.function(),
        document: t.customValidator(t.object(), (p) => p.nodeType === Node.DOCUMENT_NODE),
        insert: t.function(),
        sanitize: t.function(),
        selectedText: t.string().optional(""),
    });

    prompt = signal("", { type: t.string() });

    setup() {
        this.state = proxy({
            result: "",
            error: "",
            loading: false,
        });
        this.history = [];
        this.pending = null;
        onWillDestroy(() => this.pending?.abort?.());
    }

    get placeholder() {
        return this.state.result
            ? _t("Ask for changes, e.g. shorter or more formal")
            : _t("Describe what to write, e.g. a short welcome text for new customers");
    }

    get preview() {
        const fragment = textToFragment(this.state.result, this.props.baseContainer, this.props.document);
        const wrapper = this.props.document.createElement("div");
        wrapper.appendChild(fragment);
        return markup(wrapper.innerHTML);
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
            this.generate();
        }
    }

    async generate() {
        let prompt = this.prompt().trim();
        if (!prompt || this.state.loading) {
            return;
        }
        if (!this.history.length && this.props.selectedText.trim()) {
            prompt = `${prompt}\n\n${_t("Text:")}\n${this.props.selectedText}`;
        }
        this.state.loading = true;
        this.state.error = "";
        try {
            this.pending = rpc(
                "/html_editor/generate_text",
                { prompt, conversation_history: this.history },
                { silent: true }
            );
            const content = await this.pending;
            this.history.push({ role: "user", content: prompt }, { role: "assistant", content });
            this.state.result = content;
            this.prompt.set("");
        } catch (error) {
            this.state.error = error.data?.message || error.message || _t("The AI did not answer.");
        } finally {
            this.pending = null;
            this.state.loading = false;
        }
    }

    insert() {
        const fragment = textToFragment(this.state.result, this.props.baseContainer, this.props.document);
        this.props.sanitize(fragment);
        this.props.close();
        this.props.insert(fragment);
    }
}
