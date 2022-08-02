import base64

from algosdk.account import generate_account
from algosdk.future.transaction import SuggestedParams


from .teal import TealProgram  # noqa
from .tealish import TealishProgram  # noqa
from .exceptions import LogicEvalError, LogicSigReject  # noqa
from .ledger import JigLedger  # noqa


def get_suggested_params():
    sp = SuggestedParams(
        fee=1000,
        first=1,
        last=1000,
        min_fee=1000,
        flat_fee=True,
        gh=base64.b64encode(b'\x9b\x01\x08\xe3\xf2Q-6\x1f\xd9\x01z\x9c\x07\x8a`\xe3\x8dR\xc5D\xe9<W\xeb\xd89\xa9\xb9\xdfw@') # noqa
    )
    return sp


def generate_accounts(n=10):
    addresses = []
    secrets = []
    for _ in range(n):
        sk, pk = generate_account()
        addresses.append(pk)
        secrets.append(sk)
    return secrets, addresses
