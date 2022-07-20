

import secrets
import unittest
from algojig import JigLedger, sp, generate_accounts
from algosdk.future.transaction import (PaymentTxn, assign_group_id, 
    LogicSigTransaction, LogicSigAccount, ApplicationNoOpTxn, AssetTransferTxn)
from algojig.teal import TealProgram


secrets, addresses = generate_accounts(10)

addresses[0] = 'HSEZPJKIVVY46JL55D7UAIBHDNLCUGCV2OGKHY3DZWU3AKAASFW7DSRDVU'
secrets[0] = 'joZ92l+nlvGnuvzpMTHDnPyfqY/Zcuky/hgXNN2jjWQ8iZelSK1xzyV96P9AICcbVioYVdOMo+NjzamwKACRbQ=='


class TestDebug(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        pass

    def setUp(self):
        self.ledger = JigLedger()

    def test_pass(self):
        self.ledger.set_account_balance(addresses[0], 1_000_000)
        transactions = [
            PaymentTxn(
                sender=addresses[0],
                sp=sp,
                receiver=addresses[0],
                amt=100,
            ).sign(secrets[0]),
        ]

        block = self.ledger.eval_transactions(transactions)
        self.assertEqual(len(block[b'txns']), 1)

    def test_fail_overspend(self):
        transactions = [
            PaymentTxn(
                sender=addresses[0],
                sp=sp,
                receiver=addresses[0],
                amt=100,
            ).sign(secrets[0]),
        ]
        with self.assertRaises(Exception) as e:
            block = self.ledger.eval_transactions(transactions)
        self.assertIn('overspend', e.exception.args[0])

    def test_fail_fee(self):
        self.ledger.set_account_balance(addresses[0], 1_000_000)
        transactions = [
            PaymentTxn(
                sender=addresses[0],
                sp=sp,
                receiver=addresses[0],
                amt=100,
            ),
        ]
        transactions[0].fee = 0
        stxns = [
            transactions[0].sign(secrets[0]),
        ]
        with self.assertRaises(Exception) as e:
            block = self.ledger.eval_transactions(stxns)
        self.assertIn('in fees, which is less than the minimum', e.exception.args[0])

    def test_pass_group(self):
        self.ledger.set_account_balance(addresses[0], 1_000_000)
        transactions = [
            PaymentTxn(
                sender=addresses[0],
                sp=sp,
                receiver=addresses[1],
                amt=200_000,
            ),
            PaymentTxn(
                sender=addresses[1],
                sp=sp,
                receiver=addresses[0],
                amt=1,
            ),
        ]
        txn_group = assign_group_id(transactions)
        stxns = [
            txn_group[0].sign(secrets[0]),
            txn_group[1].sign(secrets[1])
        ]
        block = self.ledger.eval_transactions(stxns)
        self.assertEqual(len(block[b'txns']), 2)

    def test_pass_multiple_transactions(self):
        self.ledger.set_account_balance(addresses[0], 1_000_000)
        transactions = [
            PaymentTxn(
                sender=addresses[0],
                sp=sp,
                receiver=addresses[1],
                amt=200_000,
            ),
            PaymentTxn(
                sender=addresses[1],
                sp=sp,
                receiver=addresses[0],
                amt=1,
            ),
        ]
        # not a group
        stxns = [
            transactions[0].sign(secrets[0]),
            transactions[1].sign(secrets[1])
        ]
        block = self.ledger.eval_transactions(stxns)
        self.assertEqual(len(block[b'txns']), 2)

    def test_fail_wrong_auth(self):
        transactions = [
            PaymentTxn(
                sender=addresses[0],
                sp=sp,
                receiver=addresses[0],
                amt=100,
            ).sign(secrets[1]), # signed by 1 but sender is 0
        ]
        with self.assertRaises(Exception) as e:
            block = self.ledger.eval_transactions(transactions)
        self.assertIn('should have been authorized by', e.exception.args[0])

    def test_pass_rekey(self):
        self.ledger.set_account_balance(addresses[0], 1_000_000)
        transactions = [
            PaymentTxn(
                sender=addresses[0],
                sp=sp,
                receiver=addresses[0],
                amt=0,
                rekey_to=addresses[1]
            ),
            PaymentTxn(
                sender=addresses[0],
                sp=sp,
                receiver=addresses[0],
                amt=0,
            ),
        ]
        txn_group = assign_group_id(transactions)
        stxns = [
            txn_group[0].sign(secrets[0]),
            txn_group[1].sign(secrets[1]) # signed by 1 but sender is 0
        ]
        block = self.ledger.eval_transactions(stxns)
        self.assertEqual(len(block[b'txns']), 2)

    def test_pass_logisig(self):
        lsig = LogicSigAccount(b'\x06\x81\x01')
        address = lsig.address()
        self.ledger.set_account_balance(address, 1_000_000)
        transactions = [
            LogicSigTransaction(
                PaymentTxn(
                    sender=address,
                    sp=sp,
                    receiver=address,
                    amt=100,
                ),
                lsig
            ),
        ]
        block = self.ledger.eval_transactions(transactions)
        self.assertEqual(len(block[b'txns']), 1)

    def test_fail_logisig(self):
        p = TealProgram(teal='#pragma version 6\nint 0')
        lsig = LogicSigAccount(p.bytecode)
        address = lsig.address()
        self.ledger.set_account_balance(address, 1_000_000)
        transactions = [
            LogicSigTransaction(
                PaymentTxn(
                    sender=address,
                    sp=sp,
                    receiver=address,
                    amt=100,
                ),
                lsig
            ),
        ]
        with self.assertRaises(Exception) as e:
            block = self.ledger.eval_transactions(transactions)
        self.assertIn('rejected by logic', e.exception.args[0])

    def test_fail_logisig_pc(self):
        p = TealProgram(teal=
        """#pragma version 6
        int 1
        // a comment
        int 0
        assert
        """)
        lsig = LogicSigAccount(p.bytecode)
        address = lsig.address()
        self.ledger.set_account_balance(address, 1_000_000)
        transactions = [
            LogicSigTransaction(
                PaymentTxn(
                    sender=address,
                    sp=sp,
                    receiver=address,
                    amt=100,
                ),
                lsig
            ),
        ]
        with self.assertRaises(Exception) as e:
            block = self.ledger.eval_transactions(transactions)
        self.assertIn('rejected by logic', e.exception.args[0])
        # print(p.lookup(5))

    def test_pass_app(self):
        self.ledger.creator_sk, self.ledger.creator = secrets[0], addresses[0]
        self.ledger.set_account_balance(addresses[0], 10_000_000)
        self.ledger.create_app(11, approval_program=TealProgram(teal='#pragma version 6\nint 1'))
        transactions = [
            ApplicationNoOpTxn(
                sender=addresses[0],
                sp=sp,
                index=11
            ).sign(secrets[0]),
        ]
        block = self.ledger.eval_transactions(transactions)
        self.assertEqual(len(block[b'txns']), 1)

    def test_fail_app_reject(self):
        self.ledger.creator_sk, self.ledger.creator = secrets[0], addresses[0]
        self.ledger.set_account_balance(addresses[0], 10_000_000)
        self.ledger.create_app(11, approval_program=TealProgram(teal='#pragma version 6\nint 0'))
        transactions = [
            ApplicationNoOpTxn(
                sender=addresses[0],
                sp=sp,
                index=11
            ).sign(secrets[0]),
        ]
        with self.assertRaises(Exception) as e:
            block = self.ledger.eval_transactions(transactions)
        self.assertIn('rejected by ApprovalProgram', e.exception.args[0])

    def test_pass_app_global_get(self):
        self.ledger.creator_sk, self.ledger.creator = secrets[0], addresses[0]
        self.ledger.set_account_balance(addresses[0], 10_000_000)
        self.ledger.set_global_state(app_id=11, state={
            b'a': 1
        })
        self.ledger.create_app(11, approval_program=TealProgram(teal='#pragma version 6\nbyte "a"\napp_global_get'))
        transactions = [
            ApplicationNoOpTxn(
                sender=addresses[0],
                sp=sp,
                index=11
            ).sign(secrets[0]),
        ]
        block = self.ledger.eval_transactions(transactions)
        self.assertEqual(len(block[b'txns']), 1)

    def test_reject_app_global_get(self):
        self.ledger.creator_sk, self.ledger.creator = secrets[0], addresses[0]
        self.ledger.set_account_balance(addresses[0], 10_000_000)
        self.ledger.set_global_state(app_id=11, state={
            b'a': 0
        })
        self.ledger.create_app(11, approval_program=TealProgram(teal='#pragma version 6\nbyte "a"\napp_global_get'))
        transactions = [
            ApplicationNoOpTxn(
                sender=addresses[0],
                sp=sp,
                index=11
            ).sign(secrets[0]),
        ]
        with self.assertRaises(Exception) as e:
            block = self.ledger.eval_transactions(transactions)
        self.assertIn('rejected by ApprovalProgram', e.exception.args[0])

    def test_pass_asset_transfer(self):
        self.ledger.set_account_balance(addresses[0], 1_000_000)
        self.ledger.set_account_balance(addresses[0], 1_000, asset_id=10)
        self.ledger.set_account_balance(addresses[1], 1_000_000)
        self.ledger.set_account_balance(addresses[1], 0, asset_id=10)
        transactions = [
            AssetTransferTxn(
                sender=addresses[0],
                sp=sp,
                receiver=addresses[1],
                amt=100,
                index=10,

            ).sign(secrets[0]),
        ]

        block = self.ledger.eval_transactions(transactions)
        self.assertEqual(len(block[b'txns']), 1)
