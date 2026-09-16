import { Component, onWillStart, proxy, usePlugin, useProps } from "@odoo/owl";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { _t } from "@web/core/l10n/translation";
import { NotificationPlugin } from "@web/core/notifications/notification_plugin";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";
import { RecordSelector } from "@web/core/record_selectors/record_selector";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { formatMonetary } from "@web/views/fields/formatters";
import { parseFloat } from "@web/views/fields/parsers";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const TRANSACTION_PAGE = 80;

function emptyWriteoff(amount = 0) {
    return { account_id: false, label: "", amount, tax_ids: [], tax_included: false };
}

/**
 * Bank reconciliation: the transactions of a journal on the left, the one being reconciled on the right.
 *
 * The screen only builds a "proposal" (journal items to match and counterparts to add) and asks the
 * server for a preview of it; all the accounting is done by the engine of `account.bank.statement.line`.
 */
export class OmBankReconciliation extends Component {
    static template = "om_account_reconcile.BankReconciliation";
    static components = { ControlPanel, MultiRecordSelector, RecordSelector };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = usePlugin(NotificationPlugin);
        const params = this.props.action.params || {};
        this.state = proxy({
            journals: [],
            journalId: params.journal_id || this.props.action.context?.default_journal_id || false,
            filter: "to_reconcile",
            search: "",
            transactions: [],
            count: 0,
            selectedId: false,
            data: null,
            proposal: { partner_id: false, matches: [], writeoffs: [] },
            preview: null,
            tab: "match",
            candidateSearch: "",
            candidates: [],
            writeoff: emptyWriteoff(),
            busy: false,
        });
        this.debouncedSearchTransactions = useDebounced(() => this.loadTransactions(), 300);
        this.debouncedSearchCandidates = useDebounced(() => this.loadCandidates(), 300);

        useHotkey("control+enter", () => this.validate(), { bypassEditableProtection: true });
        useHotkey("alt+arrowdown", () => this.selectRelative(1), { bypassEditableProtection: true });
        useHotkey("alt+arrowup", () => this.selectRelative(-1), { bypassEditableProtection: true });

        onWillStart(async () => {
            await this.loadJournals();
            await this.loadTransactions();
        });
    }

    // ------------------------------------------------------------------
    // Getters
    // ------------------------------------------------------------------

    get transaction() {
        return this.state.data?.transaction;
    }

    get isReconciled() {
        return Boolean(this.transaction?.is_reconciled);
    }

    get remaining() {
        if (this.state.preview) {
            return this.state.preview.remaining;
        }
        return this.transaction ? this.transaction.remaining : 0;
    }

    get canValidate() {
        return (
            !this.state.busy &&
            this.transaction &&
            !this.isReconciled &&
            (this.state.proposal.matches.length || this.state.proposal.writeoffs.length)
        );
    }

    get matchedIds() {
        return new Set(this.state.proposal.matches.map((match) => match.aml_id));
    }

    get accountDomain() {
        return [["account_type", "!=", "off_balance"], ["active", "=", true]];
    }

    get taxDomain() {
        return [["type_tax_use", "in", ["sale", "purchase", "none"]]];
    }

    format(amount, currencyId) {
        return formatMonetary(amount, { currencyId });
    }

    formatAbs(amount, currencyId) {
        return formatMonetary(Math.abs(amount || 0), { currencyId });
    }

    // ------------------------------------------------------------------
    // Loading
    // ------------------------------------------------------------------

    async loadJournals() {
        this.state.journals = await this.orm.searchRead(
            "account.journal",
            [["type", "in", ["bank", "cash", "credit"]]],
            ["id", "display_name", "type"],
            { order: "sequence, id" }
        );
        if (!this.state.journalId && this.state.journals.length) {
            this.state.journalId = this.state.journals[0].id;
        }
    }

    async loadTransactions({ append = false } = {}) {
        const result = await this.orm.call(
            "account.bank.statement.line",
            "om_bank_rec_search_transactions",
            [],
            {
                journal_id: this.state.journalId,
                search: this.state.search,
                state: this.state.filter,
                limit: TRANSACTION_PAGE,
                offset: append ? this.state.transactions.length : 0,
            }
        );
        this.state.transactions = append
            ? [...this.state.transactions, ...result.transactions]
            : result.transactions;
        this.state.count = result.count;
        const stillListed = this.state.transactions.some((tr) => tr.id === this.state.selectedId);
        if (!stillListed) {
            const first = this.state.transactions[0];
            if (first) {
                await this.selectTransaction(first.id);
            } else {
                this.state.selectedId = false;
                this.state.data = null;
            }
        }
    }

    async selectTransaction(id, { force = false } = {}) {
        if (!force && id === this.state.selectedId && this.state.data?.transaction.id === id) {
            return;
        }
        this.state.selectedId = id;
        const data = await this.orm.call("account.bank.statement.line", "om_bank_rec_get_data", [[id]]);
        if (this.state.selectedId !== id) {
            return;
        }
        this.applyData(data);
        if (!this.isReconciled) {
            await Promise.all([this.refreshPreview(), this.loadCandidates()]);
        }
    }

    applyData(data) {
        const sameTransaction = this.state.data?.transaction.id === data.transaction.id;
        this.state.data = data;
        const transaction = data.transaction;
        const index = this.state.transactions.findIndex((tr) => tr.id === transaction.id);
        if (index >= 0) {
            this.state.transactions[index] = transaction;
        }
        this.state.proposal = {
            partner_id: transaction.partner_id || false,
            matches: data.suggestion.matches.map((match) => ({ ...match })),
            writeoffs: [],
        };
        this.state.preview = null;
        this.state.candidateSearch = "";
        this.state.writeoff = emptyWriteoff(Math.abs(transaction.remaining));
        if (!sameTransaction) {
            this.state.tab = "match";
        }
    }

    async loadCandidates() {
        if (!this.transaction || this.isReconciled) {
            this.state.candidates = [];
            return;
        }
        this.state.candidates = await this.orm.call(
            "account.bank.statement.line",
            "om_bank_rec_candidates",
            [[this.transaction.id]],
            { search: this.state.candidateSearch }
        );
    }

    async refreshPreview() {
        if (!this.transaction || this.isReconciled) {
            this.state.preview = null;
            return;
        }
        this.state.preview = await this.orm.call(
            "account.bank.statement.line",
            "om_bank_rec_preview",
            [[this.transaction.id], this.serializedProposal()]
        );
        if (!this.state.writeoff.account_id) {
            this.state.writeoff.amount = Math.abs(this.state.preview.remaining);
        }
    }

    serializedProposal() {
        const proposal = this.state.proposal;
        return {
            partner_id: proposal.partner_id,
            matches: proposal.matches.map((match) => ({ aml_id: match.aml_id, amount: match.amount })),
            writeoffs: proposal.writeoffs,
        };
    }

    // ------------------------------------------------------------------
    // Transactions list
    // ------------------------------------------------------------------

    async onJournalChange(ev) {
        this.state.journalId = parseInt(ev.target.value) || false;
        this.state.selectedId = false;
        await this.loadTransactions();
    }

    async setFilter(filter) {
        this.state.filter = filter;
        await this.loadTransactions();
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
        this.debouncedSearchTransactions();
    }

    async selectRelative(step) {
        const transactions = this.state.transactions;
        const index = transactions.findIndex((tr) => tr.id === this.state.selectedId);
        const next = transactions[index + step];
        if (next) {
            await this.selectTransaction(next.id);
        }
    }

    async loadMore() {
        await this.loadTransactions({ append: true });
    }

    async autoReconcile() {
        const ids = this.state.transactions.filter((tr) => !tr.is_reconciled).map((tr) => tr.id);
        if (!ids.length) {
            return;
        }
        this.state.busy = true;
        try {
            const count = await this.orm.call(
                "account.bank.statement.line",
                "om_bank_rec_auto_reconcile",
                [ids]
            );
            this.notification.add(
                count
                    ? _t("%s transaction(s) reconciled automatically.", count)
                    : _t("No transaction could be reconciled automatically."),
                { type: count ? "success" : "info" }
            );
        } finally {
            this.state.busy = false;
        }
        await this.loadTransactions();
        if (this.state.selectedId) {
            await this.selectTransaction(this.state.selectedId, { force: true });
        }
    }

    // ------------------------------------------------------------------
    // Proposal
    // ------------------------------------------------------------------

    async setPartner(partnerId) {
        this.state.proposal.partner_id = partnerId || false;
        await this.refreshPreview();
    }

    async addMatch(candidate) {
        if (this.matchedIds.has(candidate.id)) {
            return;
        }
        this.state.proposal.matches.push({ aml_id: candidate.id, amount: null, candidate });
        await this.refreshPreview();
    }

    async removeMatch(index) {
        this.state.proposal.matches.splice(index, 1);
        await this.refreshPreview();
    }

    async setMatchAmount(index, ev) {
        const match = this.state.proposal.matches[index];
        try {
            const value = parseFloat(ev.target.value);
            match.amount = value ? Math.abs(value) : null;
        } catch {
            this.notification.add(_t("This amount is not a number."), { type: "danger" });
            return;
        }
        await this.refreshPreview();
    }

    writeoffPreviewLine(index) {
        // the preview lists one base line per counterpart, in the order of the proposal
        const lines = (this.state.preview?.lines || []).filter((line) => line.kind === "writeoff");
        return lines[index] || {};
    }

    previewAmountFor(match) {
        const line = this.state.preview?.lines.find((line) => line.aml_id === match.aml_id);
        return line ? line.amount_currency : 0;
    }

    onCandidateSearchInput(ev) {
        this.state.candidateSearch = ev.target.value;
        this.debouncedSearchCandidates();
    }

    setWriteoffAccount(accountId) {
        this.state.writeoff.account_id = accountId || false;
    }

    setWriteoffTaxes(taxIds) {
        this.state.writeoff.tax_ids = taxIds;
    }

    setWriteoffAmount(ev) {
        try {
            this.state.writeoff.amount = Math.abs(parseFloat(ev.target.value));
        } catch {
            this.notification.add(_t("This amount is not a number."), { type: "danger" });
        }
    }

    async addWriteoff() {
        const writeoff = this.state.writeoff;
        if (!writeoff.account_id) {
            this.notification.add(_t("Choose the account of the counterpart."), { type: "warning" });
            return;
        }
        if (!writeoff.amount) {
            this.notification.add(_t("The amount of the counterpart cannot be zero."), { type: "warning" });
            return;
        }
        // the counterpart takes the direction of what is left to cover (a debit for money going out)
        const direction = this.remaining ? Math.sign(this.remaining) : -Math.sign(this.transaction.amount);
        this.state.proposal.writeoffs.push({
            ...writeoff,
            amount: direction * Math.abs(writeoff.amount),
            partner_id: this.state.proposal.partner_id,
        });
        this.state.writeoff = emptyWriteoff();
        await this.refreshPreview();
    }

    async removeWriteoff(index) {
        this.state.proposal.writeoffs.splice(index, 1);
        await this.refreshPreview();
    }

    async applyModel(model) {
        const writeoffs = await this.orm.call(
            "account.bank.statement.line",
            "om_bank_rec_model_writeoffs",
            [[this.transaction.id], model.id, this.serializedProposal()]
        );
        if (!writeoffs.length) {
            this.notification.add(_t("The model %s has nothing to add here.", model.name), { type: "info" });
            return;
        }
        this.state.proposal.writeoffs.push(...writeoffs);
        await this.refreshPreview();
    }

    async resetProposal() {
        await this.selectTransaction(this.transaction.id, { force: true });
    }

    // ------------------------------------------------------------------
    // Actions
    // ------------------------------------------------------------------

    async validate() {
        if (!this.canValidate) {
            return;
        }
        this.state.busy = true;
        const id = this.transaction.id;
        try {
            const data = await this.orm.call(
                "account.bank.statement.line",
                "om_bank_rec_validate",
                [[id], this.serializedProposal()]
            );
            this.applyData(data);
        } finally {
            this.state.busy = false;
        }
        if (this.isReconciled && this.state.filter === "to_reconcile") {
            const index = this.state.transactions.findIndex((tr) => tr.id === id);
            const next = this.state.transactions.slice(index + 1).find((tr) => !tr.is_reconciled)
                || this.state.transactions.find((tr) => !tr.is_reconciled && tr.id !== id);
            this.state.transactions = this.state.transactions.filter((tr) => tr.id !== id);
            this.state.count -= 1;
            if (next) {
                await this.selectTransaction(next.id);
            }
        } else if (!this.isReconciled) {
            await Promise.all([this.refreshPreview(), this.loadCandidates()]);
        }
    }

    async undo() {
        this.state.busy = true;
        try {
            const data = await this.orm.call("account.bank.statement.line", "om_bank_rec_undo", [
                [this.transaction.id],
            ]);
            this.applyData(data);
        } finally {
            this.state.busy = false;
        }
        await Promise.all([this.refreshPreview(), this.loadCandidates()]);
    }

    async toggleToCheck() {
        const toCheck = this.transaction.review_state !== "todo";
        const data = await this.orm.call("account.bank.statement.line", "om_bank_rec_set_review", [
            [this.transaction.id],
            toCheck,
        ]);
        this.state.data.transaction = data.transaction;
    }

    openMove(moveId) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "account.move",
            res_id: moveId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("om_bank_reconciliation", OmBankReconciliation);
