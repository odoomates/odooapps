import { Component, proxy, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";

/** The notes on one figure of a report: read them, add one, change or delete one's own. */
export class NoteDialog extends Component {
    static template = "om_report_engine.NoteDialog";
    static components = { Dialog };
    props = useProps({
        close: t.function(),
        title: t.string(),
        subtitle: t.string().optional(),
        notes: t.array(),
        onSave: t.function(),
        onDelete: t.function(),
    });

    setup() {
        this.state = proxy({ notes: this.props.notes, draft: "", editing: false, saving: false });
    }

    when(note) {
        return note.date ? formatDateTime(deserializeDateTime(note.date)) : "";
    }

    edit(note) {
        this.state.editing = note.id;
        this.state.draft = note.note;
    }

    cancel() {
        this.state.editing = false;
        this.state.draft = "";
    }

    async save() {
        if (!this.state.draft.trim() && !this.state.editing) {
            return;
        }
        this.state.saving = true;
        try {
            this.state.notes = await this.props.onSave(this.state.draft, this.state.editing);
            this.cancel();
        } finally {
            this.state.saving = false;
        }
    }

    async remove(note) {
        this.state.notes = await this.props.onDelete(note.id);
        if (this.state.editing === note.id) {
            this.cancel();
        }
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
            this.save();
        }
    }
}
