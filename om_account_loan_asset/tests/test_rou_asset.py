from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.om_account_loan.tests.common import LoanCommon


@tagged('post_install', '-at_install')
class TestRightOfUseAsset(LoanCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['account.account']
        cls.category_account = Account.create({
            'code': '152800', 'name': 'Right-of-use Buildings', 'account_type': 'asset_non_current'})
        cls.accumulated_account = Account.create({
            'code': '152890', 'name': 'Right-of-use Accumulated Depreciation', 'account_type': 'asset_non_current'})
        cls.depreciation_account = Account.create({
            'code': '681800', 'name': 'Right-of-use Depreciation', 'account_type': 'expense_depreciation'})
        cls.category = cls.env['account.asset.category'].create({
            'name': 'Leased Offices',
            'type': 'purchase',
            'journal_id': cls.misc_journal.id,
            'account_asset_id': cls.category_account.id,
            'account_depreciation_id': cls.accumulated_account.id,
            'account_depreciation_expense_id': cls.depreciation_account.id,
            'method_number': 60,
            'method_period': 1,
            'date_first_depreciation': 'last_day_period',
            'open_asset': True,
        })

    def test_rou_asset_created(self):
        """ The recognition debits the asset account of the category and creates the asset at the lease
        liability, depreciated monthly over the 12 months of the lease term. """
        lease = self._create_lease(asset_category_id=self.category.id)
        recognition = lease.operation_ids.move_id
        self.assertEqual(self._entry(recognition), {
            self.category_account.code: (11618.93, 0.0, 11618.93),
            self.lease_long_term_account.code: (0.0, 11618.93, -11618.93),
        })
        asset = lease.asset_id
        self.assertTrue(asset)
        self.assertEqual((asset.category_id, asset.value, asset.date), (self.category, 11618.93, date(2025, 1, 1)))
        self.assertEqual((asset.partner_id, asset.code, asset.currency_id), (self.lessor, lease.name,
                                                                             self.env.company.currency_id))
        self.assertEqual((asset.method, asset.method_time, asset.method_end, asset.prorata),
                         ('linear', 'end', date(2025, 12, 31), True))
        self.assertEqual(asset.state, 'open')
        board = asset._get_board_moves().sorted('date')
        self.assertEqual(len(board), 12)
        self.assertEqual((board[0].date, board[-1].date), (date(2025, 1, 31), date(2025, 12, 31)))
        self.assertAlmostEqual(sum(board.mapped('asset_depreciation_amount')), 11618.93, places=2)
        self.assertEqual(board[0].asset_depreciation_amount, 968.24)
        action = lease.action_view_rou_asset()
        self.assertEqual(action['res_id'], asset.id)

    def test_without_category(self):
        """ Without a category, no asset: the right-of-use account of the lease is debited. """
        lease = self._create_lease()
        self.assertFalse(lease.asset_id)
        self.assertIn(self.rou_account, lease.operation_ids.move_id.line_ids.account_id)

    def test_draft_asset(self):
        """ A category that does not confirm its assets leaves the asset in draft, to check. """
        self.category.open_asset = False
        lease = self._create_lease(asset_category_id=self.category.id)
        self.assertEqual(lease.asset_id.state, 'draft')

    def test_cancel_recognition_cancels_asset(self):
        lease = self._create_lease(asset_category_id=self.category.id)
        asset = lease.asset_id
        lease.operation_ids.action_cancel()
        self.assertEqual(asset.state, 'cancelled')
        self.assertFalse(lease.asset_id)
        lease.action_recognize()
        self.assertTrue(lease.asset_id)
        self.assertNotEqual(lease.asset_id, asset)

    def test_category_locked(self):
        lease = self._create_lease(asset_category_id=self.category.id)
        with self.assertRaises(UserError):
            lease.asset_category_id = False

    def test_paid_in_advance_term(self):
        """ A lease paid in advance runs one period after its last payment. """
        lease = self._create_lease(asset_category_id=self.category.id, date_first_payment=date(2025, 1, 1))
        self.assertEqual(lease.asset_id.method_end, date(2025, 12, 31))
        self.assertEqual(lease.asset_id.value, 11677.03)
