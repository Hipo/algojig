from algojig import JigLedger, get_suggested_params, generate_accounts, dump
from algojig import TealishProgram
from algosdk.future.transaction import ApplicationNoOpTxn
from algosdk.logic import get_application_address

secrets, addresses = generate_accounts(2)
sp = get_suggested_params()

p = TealishProgram(filename='examples/counter_prize.tl')

APP_ID = 1
APP_ADDRESS = get_application_address(APP_ID)

ledger = JigLedger()
ledger.create_app(APP_ID, approval_program=p)
ledger.set_account_balance(addresses[0], 1_000_000)
ledger.set_account_balance(APP_ADDRESS, 11_000_000)

transactions = [
    ApplicationNoOpTxn(
        sender=addresses[0],
        sp=sp,
        index=APP_ID,
    ).sign(secrets[0]),
]
for i in range(10):
    block = ledger.eval_transactions(transactions)
    print('ApplyData:', block[b'txns'][0][b'dt'])
    print('Global Counter:', ledger.get_global_state(APP_ID)[b'counter'])
    print('Sender Algo Balance:', ledger.get_account_balance(addresses[0], asset_id=0)[0])
    print(dump(block))
