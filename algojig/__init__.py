import base64
from pprint import pprint

from algosdk.account import generate_account
from algosdk.transaction import SuggestedParams
from algosdk.encoding import encode_address


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


def _dump(d):
    if isinstance(d, bytes):
        if len(d) == 32:
            return encode_address(d)
        return d
    elif isinstance(d, (tuple, list, set)):
        return [_dump(x) for x in d]
    elif isinstance(d, dict):
        result = {}
        keys = list(d.keys())
        values = [_dump(v) for v in d.values()]
        try:
            keys = [k.decode() if isinstance(k, bytes) else k for k in keys]
        except UnicodeDecodeError:
            pass
        result = dict(zip(keys, values))
        return result
    else:
        return d


def dump(*d):
    if len(d) == 1:
        d = d[0]
    pprint(_dump(d), indent=2)


def print_logs(logs):
    for log in logs:
        if b'%i' in log:
            i = log.index(b'%i')
            s = log[0:i].decode()
            value = int.from_bytes(log[i + 2:], 'big')
            print(f'Log: {s}: {value}')
        else:
            print(f'Log: {log}')
