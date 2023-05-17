import unittest
from algojig import JigLedger, get_suggested_params, generate_accounts
from algojig import TealishProgram
from algosdk.transaction import ApplicationNoOpTxn
from algosdk.logic import get_application_address

secrets, addresses = generate_accounts(2)
sp = get_suggested_params()

APP_ID = 1
APP_ADDRESS = get_application_address(APP_ID)


def get_transactions():
    transactions = [
        ApplicationNoOpTxn(
            sender=addresses[0],
            sp=sp,
            index=APP_ID,
        ).sign(secrets[0]),
    ]
    return transactions


program = TealishProgram(filename='examples/counter_prize.tl')


class TestCounter(unittest.TestCase):

    def setUp(self):
        self.ledger = JigLedger()
        self.ledger.create_app(APP_ID, approval_program=program)
        self.ledger.set_account_balance(addresses[0], 1_000_000)
        self.ledger.set_account_balance(APP_ADDRESS, 11_000_000)

    def test_pass_first(self):
        transactions = get_transactions()
        block = self.ledger.eval_transactions(transactions)
        txn = block[b'txns'][0]
        # Make sure no inner txns
        self.assertNotIn(b'itx', txn[b'dt'])
        # Make sure counter is now 1
        self.assertEqual(self.ledger.get_global_state(APP_ID)[b'counter'], 1)

    def test_pass_increment(self):
        self.ledger.set_global_state(APP_ID, {b'counter': 1}) 
        transactions = get_transactions()
        self.ledger.eval_transactions(transactions)
        # Make sure counter is now 2
        self.assertEqual(self.ledger.get_global_state(APP_ID)[b'counter'], 2)

    def test_pass_win(self):
        self.ledger.set_global_state(APP_ID, {b'counter': 9})
        transactions = get_transactions()
        block = self.ledger.eval_transactions(transactions)
        txn = block[b'txns'][0]
        # Make sure the amount is correct
        self.assertEqual(txn[b'dt'][b'itx'][0][b'txn'][b'amt'], 10_000_000)
        # Make sure counter is now 10
        self.assertEqual(self.ledger.get_global_state(APP_ID)[b'counter'], 10)

    def test_fail_win_again(self):
        self.ledger.set_global_state(APP_ID, {b'counter': 10}) 
        transactions = get_transactions()
        with self.assertRaises(Exception) as e:
            self.ledger.eval_transactions(transactions)
        self.assertIn('transaction rejected by ApprovalProgram', str(e.exception))
