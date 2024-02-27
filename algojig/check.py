from algojig import get_suggested_params, generate_accounts, dump
from algojig.ledger import JigLedger
from algosdk.transaction import PaymentTxn

secrets, addresses = generate_accounts(2)

sp = get_suggested_params()

ledger = JigLedger()
ledger.set_account_balance(addresses[0], 1_000_000)

transactions = [
    PaymentTxn(
        sender=addresses[0],
        sp=sp,
        receiver=addresses[1],
        amt=200_000,
    ).sign(secrets[0]),
]
block = ledger.eval_transactions(transactions)
print("Looks like it works!")
