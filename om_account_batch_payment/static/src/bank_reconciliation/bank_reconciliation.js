import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { OmBankReconciliation } from "@om_account_reconcile/bank_reconciliation/bank_reconciliation";

/**
 * Batches tab: one transaction of the bank clearing all the payments of a batch. Adding a batch adds the
 * journal items of its payments to the proposal; each of them remembers its payments, so that the server
 * knows which payments the validated proposal cleared.
 */
patch(OmBankReconciliation.prototype, {
    setup() {
        super.setup(...arguments);
        this.state.batches = [];
    },

    applyData(data) {
        super.applyData(...arguments);
        if (data.suggestion.writeoffs?.length) {
            this.state.proposal.writeoffs = data.suggestion.writeoffs.map((writeoff) => ({ ...writeoff }));
        }
    },

    async loadCandidates() {
        await super.loadCandidates(...arguments);
        if (!this.transaction || this.isReconciled) {
            this.state.batches = [];
            return;
        }
        this.state.batches = await this.orm.call(
            "account.bank.statement.line",
            "om_bank_rec_batches",
            [[this.transaction.id]],
            { search: this.state.candidateSearch }
        );
    },

    serializedProposal() {
        const result = super.serializedProposal(...arguments);
        const paymentIds = new Set();
        for (const line of [...this.state.proposal.matches, ...this.state.proposal.writeoffs]) {
            for (const paymentId of line.payment_ids || []) {
                paymentIds.add(paymentId);
            }
        }
        result.batch_payment_ids = [...paymentIds];
        return result;
    },

    get batchPaymentIds() {
        return new Set(this.serializedProposal().batch_payment_ids);
    },

    async addBatch(batch) {
        const proposal = await this.orm.call(
            "account.bank.statement.line",
            "om_bank_rec_batch_proposal",
            [[this.transaction.id], batch.id]
        );
        const known = this.batchPaymentIds;
        const matches = proposal.matches.filter((match) => !this.matchedIds.has(match.aml_id));
        const writeoffs = proposal.writeoffs.filter(
            (writeoff) => !writeoff.payment_ids.some((paymentId) => known.has(paymentId))
        );
        if (!matches.length && !writeoffs.length) {
            this.notification.add(_t("The batch %s is already in the proposal.", batch.name), { type: "info" });
            return;
        }
        this.state.proposal.matches.push(...matches);
        this.state.proposal.writeoffs.push(...writeoffs);
        await this.refreshPreview();
    },
});
