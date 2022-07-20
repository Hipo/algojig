import base64
from .teal import TealProgram
from .tealish import TealishProgram
from .exceptions import LogicEvalError, LogicSigReject
from algosdk.future.transaction import SuggestedParams


sp = SuggestedParams(
    fee=1000,
    first=1,
    last=1000,
    min_fee=1000,
    flat_fee=True,
    gh=base64.b64encode(b'\x9b\x01\x08\xe3\xf2Q-6\x1f\xd9\x01z\x9c\x07\x8a`\xe3\x8dR\xc5D\xe9<W\xeb\xd89\xa9\xb9\xdfw@')
)
