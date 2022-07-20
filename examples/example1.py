from algojig import JigLedger, sp, generate_accounts
from algosdk.future.transaction import PaymentTxn

secrets, addresses = generate_accounts(2)

ledger = JigLedger()
ledger.set_account_balance(addresses[0], 1_000_000)

transactions = [
    PaymentTxn(
        sender=addresses[0],
        sp=sp,
        receiver=addresses[1],
        amt=200_000,
    ).sign(secrets[0]),
    PaymentTxn(
        sender=addresses[1],
        sp=sp,
        receiver=addresses[0],
        amt=1,
    ).sign(secrets[1]),
]
block = ledger.eval_transactions(transactions)
print(block[b'txns'])
