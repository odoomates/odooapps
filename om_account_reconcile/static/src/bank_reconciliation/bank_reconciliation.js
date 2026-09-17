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
            // "bank" clears the transactions of the bank, "open_items" the invoices against the payments
            mode: params.mode || "bank",
            accountType: "receivable",
            groups: [],
            groupCount: 0,
            selectedGroup: null,
            openItems: [],
            openItemTotals: { debit: 0, credit: 0, clearable: 0 },
            pickedItemIds: [],
            // what closes the rest of a partial settlement: a discount, a bad debt, a rounding
            itemWriteoff: { enabled: false, account_id: false, journal_id: false, label: "" },
            journals: [],
            journalId: params.journal_id || this.props.action.context?.default_journal_id || false,
            filter: params.filter || "to_reconcile",
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
        this.debouncedSearchGroups = useDebounced(() => this.loadGroups(), 300);

        useHotkey("control+enter", () => this.validate(), { bypassEditableProtection: true });
        useHotkey("alt+arrowdown", () => this.selectRelative(1), { bypassEditableProtection: true });
        useHotkey("alt+arrowup", () => this.selectRelative(-1), { bypassEditableProtection: true });

        onWillStart(async () => {
            await this.loadJournals();
            if (this.state.mode === "open_items") {
                await this.loadGroups();
            } else {
                await this.loadTransactions();
                if (params.st_line_id) {
                    await this.selectTransaction(params.st_line_id);
                }
            }
        });
    }

    // ------------------------------------------------------------------
    // Open items: the invoices and the payments that clear each other
    // ------------------------------------------------------------------

    async setMode(mode) {
        if (this.state.mode === mode) {
            return;
        }
        this.state.mode = mode;
        this.state.search = "";
        if (mode === "open_items") {
            await this.loadGroups();
        } else {
            await this.loadTransactions();
        }
    }

    onOpenItemsSearchInput(ev) {
        this.state.search = ev.target.value;
        this.debouncedSearchGroups();
    }

    async setAccountType(accountType) {
        this.state.accountType = accountType;
        this.state.selectedGroup = null;
        this.state.openItems = [];
        this.state.pickedItemIds = [];
        await this.loadGroups();
    }

    async loadGroups() {
        const result = await this.orm.call("account.move.line", "om_open_items_search_groups", [], {
            account_type: this.state.accountType,
            search: this.state.search,
        });
        this.state.groups = result.groups;
        this.state.groupCount = result.count;
        const selected = this.state.selectedGroup;
        if (selected && !result.groups.some((group) => this.sameGroup(group, selected))) {
            this.state.selectedGroup = null;
            this.state.openItems = [];
            this.state.pickedItemIds = [];
        }
    }

    sameGroup(one, other) {
        return one.partner_id === other.partner_id && one.account_id === other.account_id;
    }

    async selectGroup(group) {
        this.state.selectedGroup = group;
        const result = await this.orm.call("account.move.line", "om_open_items_get_lines", [
            group.partner_id,
            group.account_id,
        ]);
        this.state.openItems = result.lines;
        this.state.openItemTotals = {
            debit: result.debit,
            credit: result.credit,
            clearable: result.clearable,
        };
        // what an accountant would pick: the oldest items of both sides that cancel out
        this.state.pickedItemIds = result.suggestion || [];
    }

    toggleItem(itemId) {
        const picked = this.state.pickedItemIds;
        this.state.pickedItemIds = picked.includes(itemId)
            ? picked.filter((id) => id !== itemId)
            : [...picked, itemId];
    }

    isPicked(itemId) {
        return this.state.pickedItemIds.includes(itemId);
    }

    get pickedItems() {
        return this.state.openItems.filter((item) => this.isPicked(item.id));
    }

    get pickedDifference() {
        return this.pickedItems.reduce((total, item) => total + item.amount_residual, 0);
    }

    get canReconcileItems() {
        // what is owed and what settles it: items all on the same side settle nothing
        const picked = this.pickedItems;
        return (
            picked.length > 1 &&
            picked.some((item) => item.amount_residual > 0) &&
            picked.some((item) => item.amount_residual < 0) &&
            !this.state.busy
        );
    }

    get stillOpenAfter() {
        /** What is left open once the picked items are reconciled: a partial payment leaves the rest. */
        return this.pickedDifference;
    }

    get canWriteOffItems() {
        return this.canReconcileItems && !!this.stillOpenAfter;
    }

    get itemWriteoffReady() {
        const writeoff = this.state.itemWriteoff;
        return !!(writeoff.enabled && writeoff.account_id && writeoff.journal_id);
    }

    toggleItemWriteoff() {
        const writeoff = this.state.itemWriteoff;
        writeoff.enabled = !writeoff.enabled;
        if (writeoff.enabled && !writeoff.journal_id) {
            writeoff.journal_id = this.state.journals[0]?.id || false;
        }
    }

    setItemWriteoffAccount(accountId) {
        this.state.itemWriteoff.account_id = accountId || false;
    }

    setItemWriteoffJournal(journalId) {
        this.state.itemWriteoff.journal_id = journalId || false;
    }

    setItemWriteoffLabel(ev) {
        this.state.itemWriteoff.label = ev.target.value;
    }

    async reconcileItems() {
        if (!this.canReconcileItems) {
            return;
        }
        const writeoff = this.state.itemWriteoff;
        if (writeoff.enabled && !this.itemWriteoffReady) {
            this.notification.add(_t("Choose the account and the journal of the write-off."), {
                type: "warning",
            });
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call("account.move.line", "om_open_items_reconcile", [
                this.state.pickedItemIds,
                writeoff.enabled && this.stillOpenAfter
                    ? {
                          account_id: writeoff.account_id,
                          journal_id: writeoff.journal_id,
                          label: writeoff.label,
                      }
                    : null,
            ]);
            this.state.itemWriteoff = {
                enabled: false,
                account_id: false,
                journal_id: false,
                label: "",
            };
            this.notification.add(_t("The journal items are reconciled."), { type: "success" });
            const group = this.state.selectedGroup;
            await this.loadGroups();
            const still = this.state.groups.find((candidate) => this.sameGroup(candidate, group));
            if (still) {
                await this.selectGroup(still);
            } else {
                this.state.selectedGroup = null;
                this.state.openItems = [];
                this.state.pickedItemIds = [];
            }
        } finally {
            this.state.busy = false;
        }
    }

    openJournal() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: _t("Transactions"),
            res_model: "account.bank.statement.line",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: [["journal_id", "=", this.state.journalId]],
            context: { default_journal_id: this.state.journalId },
        });
    }

    openItemMove(item) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "account.move",
            res_id: item.move_id,
            views: [[false, "form"]],
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
