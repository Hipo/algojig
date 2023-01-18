from algojig import JigLedger, get_suggested_params, generate_accounts
from algojig import TealishProgram
from algosdk.future.transaction import ApplicationNoOpTxn
from algosdk.logic import get_application_address

secrets, addresses = generate_accounts(2)
sp = get_suggested_params()

p = TealishProgram(tealish="""
    #pragma version 8

    int exists
    bytes value
    exists, value = box_get("box1")
    assert(exists)
    log(value)

    box_put("box1", "foo")

    _ = box_del("box2")
    exit(1)
""".strip())

APP_ID = 1
ledger = JigLedger()
ledger.create_app(APP_ID, approval_program=p)
ledger.set_account_balance(addresses[0], 1_000_000)

ledger.set_account_balance(get_application_address(APP_ID), 1_000_000)
ledger.set_box(APP_ID, b"box1", b"abc")
ledger.set_box(APP_ID, b"box2", b"xyz")

transactions = [
    ApplicationNoOpTxn(
        sender=addresses[0],
        sp=sp,
        index=APP_ID,
        boxes=[(0, "box1"), (0, "box2")]
    ).sign(secrets[0]),
]
block = ledger.eval_transactions(transactions)
print('Logs', block[b'txns'][0][b'dt'][b'lg'])
print('Boxes', ledger.boxes)

assert ledger.get_box(APP_ID, b"box1") == b"foo"
assert ledger.box_exists(APP_ID, b"box2") is False
