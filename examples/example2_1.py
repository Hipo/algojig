from algojig import JigLedger, get_suggested_params, generate_accounts, dump
from algojig import TealProgram
from algosdk.future.transaction import ApplicationNoOpTxn

secrets, addresses = generate_accounts(2)
sp = get_suggested_params()

p = TealProgram(teal="""
    #pragma version 6
    // increment global counter
    pushbytes "counter"
    dup
    app_global_get
    int 1
    +
    app_global_put

    // increment local counter
    int 0
    pushbytes "counter"
    dup2
    app_local_get
    int 1
    +
    app_local_put
    int 1
""")

APP_ID = 1

ledger = JigLedger()
ledger.create_app(APP_ID, approval_program=p)
ledger.set_account_balance(addresses[0], 1_000_000)
ledger.set_local_state(addresses[0], APP_ID, {})
ledger.set_global_state(APP_ID, {b'counter': 100})

transactions = [
    ApplicationNoOpTxn(
        sender=addresses[0],
        sp=sp,
        index=APP_ID,
        accounts=[]
    ).sign(secrets[0]),
]
block = ledger.eval_transactions(transactions)
print(block[b'txns'])
print('Algo Balance 0:', ledger.get_account_balance(addresses[0]))
print()
print('Account 0:', addresses[0])
dump(ledger.get_raw_account(addresses[0]))
print()
print('Creator:', ledger.creator)
dump(ledger.get_raw_account(ledger.creator))

print()
print('Global Counter:', ledger.get_global_state(APP_ID)[b'counter'])
print('Local Counter:', ledger.get_local_state(addresses[0], APP_ID)[b'counter'])

block = ledger.eval_transactions(transactions)
print('Global Counter:', ledger.get_global_state(APP_ID)[b'counter'])
print('Local Counter:', ledger.get_local_state(addresses[0], APP_ID)[b'counter'])

block = ledger.eval_transactions(transactions)
print('Global Counter:', ledger.get_global_state(APP_ID)[b'counter'])
print('Local Counter:', ledger.get_local_state(addresses[0], APP_ID)[b'counter'])