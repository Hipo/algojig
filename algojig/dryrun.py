import base64
from dataclasses import dataclass
from typing import Dict, List
import algosdk
from algosdk.future.transaction import SuggestedParams
from algosdk.v2client import models
from algosdk.v2client.algod import AlgodClient
from algosdk.encoding import encode_address
from .program import read_program
from .teal import TealProgram

try:
    from .tealish import TealishProgram
except ImportError:
    pass


@dataclass
class AppCallResponse:
    response: Dict
    logs: List
    inner_txns: List
    result: str
    error: str
    reason: str
    cost: int
    stack: List
    global_delta: Dict
    local_deltas: Dict


class AppCallReject(Exception):
    def __init__(self, result) -> None:
        self.message = 'AppCall Reject'
        self.result = result
        self.reason = result.reason
    
    def __str__(self) -> str:
        return self.reason


sp = SuggestedParams(
    fee=1000,
    first=1,
    last=1000,
    min_fee=1000,
    flat_fee=True,
    gh=base64.b64encode(b'\x9b\x01\x08\xe3\xf2Q-6\x1f\xd9\x01z\x9c\x07\x8a`\xe3\x8dR\xc5D\xe9<W\xeb\xd89\xa9\xb9\xdfw@')
)


class AVM:
    def __init__(self, algod: AlgodClient):
        self.algod = algod
        self.apps = {}
        self.accounts = {}
        self.assets = {}
        self.logs = []
        self.creator_sk, self.creator = algosdk.account.generate_account()

    def set_app(self, app_id, approval_filename=None, approval_program=None):
        if approval_program is None:
            approval_program = read_program(approval_filename, self.algod)
        self.apps[app_id] = {
            'app_id': app_id,
            'approval_program': approval_program,
            'creator': self.creator,
        }
    
    def get_balance(self, address, asset_id=0):
        if address not in self.accounts:
            return 0
        if asset_id not in self.accounts[address]['balances']:
            return 0
        return self.accounts[address]['balances'][asset_id]

    def set_account_balance(self, address, balance, asset_id=0):
        if address not in self.accounts:
            self.accounts[address] = {'address': address, 'local_states': {}, 'balances': {}}
        if asset_id and asset_id not in self.assets:
            self.create_asset(asset_id=asset_id)
        self.accounts[address]['balances'][asset_id] = balance

    def create_asset(self, params={}, asset_id=None):
        if asset_id is None:
            caid = 0
            for id in self.apps:
                if id > caid:
                    caid = id + 1
            for id in self.assets:
                if id > caid:
                    caid = id + 1
            asset_id = caid
        if asset_id and asset_id not in self.assets:
            self.assets[asset_id] = params
        if 'creator' in params:
            self.set_account_balance(params['creator'], params['total'], asset_id=asset_id)
        return asset_id

    def set_account_local_state(self, address, app_id, state):
        self.accounts[address]['local_states'][app_id] = state
        if state is None:
            del self.accounts[address]['local_states'][app_id]

    def set_account_auth_addr(self, address, auth_addr):
        self.accounts[address]['auth_addr'] = auth_addr

    def log(self, log):
        self.logs.append(log)

    def move(self, from_address, to_address, asset_id, amount):
        self.accounts[from_address]['balances'][asset_id] -= amount
        if to_address not in self.accounts:
            self.set_account_balance(to_address, 0)
        if asset_id not in self.accounts[to_address]['balances']:
            raise Exception(f'Account {to_address} not opted into asset {asset_id}')
        self.accounts[to_address]['balances'][asset_id] += amount

    def optin_asset(self, address, asset_id):
        self.set_account_balance(address, 0, asset_id)

    def pay_fee(self, txn):
        self.move(encode_address(txn[b'txn'][b'snd']), 'A7NMWS3NT3IUDMLVO26ULGXGIIOUQ3ND2TXSER6EBGRZNOBOUIQXHIBGDE', 0, txn[b'txn'].get(b'fee', 0))

    def eval_transactions(self, txn_group):
        txns = []
        for i, stxn in enumerate(txn_group):
            s = algosdk.encoding.msgpack_encode(stxn)
            d = algosdk.encoding.msgpack.unpackb(base64.b64decode(s), raw=True)
            txns.append(d)
            self.preprocess_transaction(d)
            if d[b'txn'][b'type'] == b'appl':
                result = self._app_call(txn_group, i)
                if result.result != 'PASS':
                    raise AppCallReject(result)
                d[b'dt'] = result.response.get(b'apply-data', {}).get(b'dt', {})
            self.process_transaction(d)
        return txns

    def preprocess_transaction(self, txn):
        self.pay_fee(txn)
        if txn[b'txn'].get(b'rekey'):
            self.set_account_auth_addr(encode_address(txn[b'txn'][b'snd']), encode_address(txn[b'txn'][b'rekey']))

    def process_transaction(self, txn):
        print(txn[b'txn'][b'type'])
        if txn[b'txn'][b'type'] == b'appl':
            if inners := txn.get(b'dt', {}).get(b'itx'):
                for itxn in inners:
                    self.preprocess_transaction(itxn)
                    self.process_transaction(itxn)
            if logs := txn.get(b'dt', {}).get(b'lg'):
                for l in logs:
                    if b'%i' in l:
                        i = l.index(b'%i')
                        s = l[0:i].decode()
                        value = int.from_bytes(l[i+2:], 'big')
                        self.log(f'{s}: {value}')
                    else:
                        self.log(f'{l}')
        elif txn[b'txn'][b'type'] == b'axfer':
            if txn[b'txn'][b'snd'] == txn[b'txn'][b'arcv'] and txn[b'txn'].get(b'aamt', 0) == 0:
                self.optin_asset(encode_address(txn[b'txn'][b'snd']), txn[b'txn'][b'xaid'])
            else:
                self.move(encode_address(txn[b'txn'][b'snd']), encode_address(txn[b'txn'][b'arcv']), txn[b'txn'][b'xaid'], txn[b'txn'][b'aamt'])
        elif txn[b'txn'][b'type'] == b'pay':
            self.move(encode_address(txn[b'txn'][b'snd']), encode_address(txn[b'txn'][b'rcv']), 0, txn[b'txn'][b'amt'])
        elif txn[b'txn'][b'type'] == b'acfg':
            if txn[b'txn'].get(b'caid', 0) == 0:
                print('create asset', txn.get(b'caid', None))
                params = {
                    'total': txn.get(b't', 0),
                    'creator': encode_address(txn[b'txn'][b'snd']),
                }
                caid = self.create_asset(params, asset_id=txn.get(b'caid', None))
                txn[b'caid'] = caid

    def dryrun2(self, drr):
        req = "/teal/dryrun2"
        headers = {"Content-Type": "application/msgpack"}
        data = algosdk.encoding.msgpack_encode(drr)
        data = base64.b64decode(data)
        return self.algod.algod_request("POST", req, data=data, response_format='msgpack', headers=headers)
    
    def app_call(self, txn_group, transaction_index):
        return self._app_call(txn_group, transaction_index)

    def _app_call(self, txn_group, transaction_index):
        apps = [
            models.Application(
                id=a['app_id'],
                params=models.ApplicationParams(
                    creator=a['creator'],
                    approval_program=a['approval_program'].bytecode,
                    clear_state_program='',
                    local_state_schema=models.ApplicationStateSchema(16, 16),
                    global_state_schema=models.ApplicationStateSchema(64, 64),
                ),
            )
        for a in self.apps.values()]

        accounts = [
            models.Account(
                address=a['address'],
                amount=a['balances'][0],
                amount_without_pending_rewards=a['balances'][0],
                auth_addr=a.get('auth_addr'),
                status='Online',
                apps_local_state=[
                    models.ApplicationLocalState(id=i, schema=models.ApplicationStateSchema(16, 16), 
                        key_value=[
                            models.TealKeyValue(base64.b64encode(k).decode(), models.TealValue(type=2, uint=v) if type(v) == int else models.TealValue(type=1, bytes=v))
                             for (k,v) in a['local_states'][i].items()
                        ]
                    )
                    for i in a['local_states']
                ],
                assets=[
                    {
                        'amount': a['balances'][id],
                        'asset-id': id,
                    } for id in a['balances'] if id > 0
                ],

            )
        for a in self.accounts.values()]

        models.AssetHolding

        accounts.append(models.Account(
            address='BLITMUHUPIO33MDDVQHUOYTGDUXRSGY2SDSY76DZDYEC5C2S7ZISLPMROQ',
            amount=10_000_000,
            amount_without_pending_rewards=10_000_000,
            status='Online',
            created_assets=[
                models.Asset(aid, models.AssetParams()) for aid in self.assets
            ]
        ))

        accounts.append(models.Account(
            address=self.creator,
            amount=10_000_000,
            amount_without_pending_rewards=10_000_000,
            status='Online',
            created_apps=apps,
        ))

        drr = {
            'accounts': [x.dictify() for x in accounts],
            'txns': [x.dictify() for x in txn_group],
            'apps': [x.dictify() for x in apps],
            'txn-index': transaction_index,
            'latest-timestamp': 1656680532,
        }

        response = self.dryrun2(drr)
        response = algosdk.encoding.msgpack.unpackb(response, raw=True, strict_map_key=False)
        # print(response.get('apply-data'))

        response['txn_group'] = txn_group
        txn = response[b'debug']
        apply_data = response.get(b'apply-data', {}).get(b'dt', {})
        # print(apply_data)
        if response[b'error']:
            raise Exception(response[b'error'])
        result = AppCallResponse(
            response=response,
            result=txn[b'app-call-messages'][1].decode(),
            error=txn[b'app-call-messages'][-1].decode(),
            reason=None,
            stack=[],
            cost=txn[b'cost'],
            inner_txns = apply_data.get(b'itx', []),
            logs=[],
            local_deltas={},
            global_delta={},
        )
        # logs = [base64.b64decode(l) for l in txn.get('logs', [])]
        # txn['logs'] = logs
        # for l in logs:
        #     if b'%i' in l:
        #         i = l.index(b'%i')
        #         s = l[0:i].decode()
        #         value = int.from_bytes(l[i+2:], 'big')
        #         result.logs.append(f'Log: {s}: {value}')
        #     else:
        #         result.logs.append(f'Log: {l}')
        # for d in txn.get('global-delta', []):
        #     result.global_delta[base64.b64decode(d['key'])] = d['value']

        for ld in apply_data.get(b'ld', {}),:
            delta = {}
            for i in ld:
                if i == 0:
                    addr = txn_group[transaction_index].transaction.sender
                else:
                    addr = txn_group[transaction_index].transaction.accounts[i - 1]
                result.local_deltas[addr] = ld[i]

        app_id = txn_group[transaction_index].transaction.index
        program = self.apps[app_id]['approval_program']
        eval_result = txn[b'app-call-messages'][1].decode()
        if txn[b'app-call-trace'][-1].get(b'error'):
            line = txn[b'app-call-trace'][-1][b'line'] + 1
            error = txn[b'app-call-trace'][-1][b'error'].decode()
            teal_line, tealish_line = program.source_map[line]
            result.reason = f'Error in program: {line}, teal: {teal_line}, tealish: {tealish_line}; {error}'
            result.stack = txn[b'app-call-trace'][-1][b'stack']
        else:
            line = txn[b'app-call-trace'][-2][b'line']
            teal_line, tealish_line = program.source_map[line]
            result.reason = f'{eval_result} from program: {line}, teal: {teal_line}, tealish: {tealish_line}'
        return result


    def print_response(self, response):
        print('- ' * 40)
        for gi, txn in enumerate(response['txns']):
            if txn.get('logic-sig-messages'):
                print('LogicSig:', txn['logic-sig-messages'])

            if not txn.get('app-call-trace'):
                continue
            app_id = response['txn_group'][gi].transaction.index
            program = self.apps[app_id]['approval_program']
            disassembly = txn['disassembly'] or []
            for i, l in enumerate(disassembly[:-1]):
                if l[0] != program.min_teal[i][0]:
                    if not (':' in l and ':' in program.min_teal[i]):
                        print('\n'.join(['...'] + [f'{j+i-5+1} {x}' for (j, x) in enumerate(disassembly[i-5:i+5])] + ['...']))
                        raise Exception(f'Disassemly different to program_min: {i+1}: {l} <> {program.min_teal[i]}')
            for l in txn['app-call-trace']:
                i, tli = program.source_map.get(l['line'], [0, 0])
                # print()
                # print(l)
                stack =  [s['bytes'] if s['type'] == 1 else s['uint'] for s in l['stack']]
                # print(tli, i, l['line'], disassembly[l['line']-1], teal[i-1], stack)
            
            if txn['app-call-trace'][-1].get('error'):
                result = txn['app-call-messages'][1]
                line = txn['app-call-trace'][-1]['line'] + 1
                error = txn['app-call-trace'][-1]['error']
                teal_line, tealish_line = program.source_map[line]
                print(f'Error in program: {line}, teal: {teal_line}, tealish: {tealish_line}; {error}')
                print('Final Stack:', txn['app-call-trace'][-1]['stack'])
            else:
                result = txn['app-call-messages'][1]
                line = txn['app-call-trace'][-2]['line']
                teal_line, tealish_line = program.source_map[line]
                print(f'{result} from program: {line}, teal: {teal_line}, tealish: {tealish_line}')

            print('Bytecode Size:', len(program.bytecode))
            print('Cost:', txn['cost'])
            logs = [base64.b64decode(l) for l in txn.get('logs', [])]
            txn['logs'] = logs
            for l in logs:
                if b'%i' in l:
                    i = l.index(b'%i')
                    s = l[0:i].decode()
                    value = int.from_bytes(l[i+2:], 'big')
                    print(f'Log: {s}: {value}')
                else:
                    print(f'Log: {l}')
            if 'global-delta' in txn:
                print('Global State Delta:')
                for d in txn['global-delta']:
                    print(' ', base64.b64decode(d['key']), ':', d['value'])
            if 'local-deltas' in txn:
                print('Local State Deltas:')
                for ld in txn['local-deltas']:
                    if ld['delta']:
                        print(f' Address: {ld["address"]}')
                        for d in ld['delta']:
                            print('  ', base64.b64decode(d['key']), ':', d['value'])
