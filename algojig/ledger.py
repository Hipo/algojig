import re
import sqlite3
from algosdk.encoding import decode_address, msgpack_encode, encode_address
from algosdk.encoding import msgpack
from algosdk.future.transaction import write_to_file
from algosdk.account import generate_account
from .program import read_program
from . import gojig
from .exceptions import LogicEvalError, LogicSigReject


class JigLedger:
    def __init__(self):
        self.filename = '/tmp/jig/jig_ledger.sqlite3.tracker.sqlite'
        self.stxn_filename = '/tmp/jig/stxns'
        self.db = None
        self.apps = {}
        self.assets = {}
        self.accounts = {}
        self.global_states = {}
        self.creator_sk, self.creator = generate_account()
        self.set_account_balance(self.creator, 100_000_000)
    
    def open_db(self):
        self.db = sqlite3.connect(self.filename)

    def set_account_balance(self, address, balance, asset_id=0, frozen=False):
        if address not in self.accounts:
            self.accounts[address] = {'address': address, 'local_states': {}, 'balances': {}}
        if asset_id and asset_id not in self.assets:
            self.create_asset(asset_id)
        if asset_id not in self.accounts[address]['balances']:
            self.accounts[address]['balances'][asset_id] = [balance, frozen]

    def create_asset(self, asset_id, params=None):
        if asset_id is None:
            caid = 0
            for id in self.apps:
                if id > caid:
                    caid = id + 1
            for id in self.assets:
                if id > caid:
                    caid = id + 1
            asset_id = caid
        params = params or {}
        if asset_id and asset_id not in self.assets:
            self.assets[asset_id] = params
        if 'creator' not in params:
            params['creator'] = self.creator
        if 'total' not in params:
            params['total'] = (2**64 - 1)
        if 'unit_name' not in params:
            params['unit_name'] = 'TEST'
        self.set_account_balance(params['creator'], params['total'], asset_id=asset_id)
        return asset_id

    def create_app(self, app_id, approval_filename=None, approval_program=None, creator=None, local_ints=16, local_bytes=16, global_ints=64, global_bytes=64):
        if approval_program is None:
            approval_program = read_program(approval_filename)
        self.apps[app_id] = {
            'app_id': app_id,
            'approval_program': approval_program,
            'creator': creator or self.creator,
            'local_ints': local_ints,
            'local_bytes': local_bytes,
            'global_ints': global_ints,
            'global_bytes': global_bytes,
        }

    def set_local_state(self, address, app_id, state):
        self.accounts[address]['local_states'][app_id] = state
        if state is None:
            del self.accounts[address]['local_states'][app_id]

    def set_auth_addr(self, address, auth_addr):
        self.accounts[address]['auth_addr'] = auth_addr

    def set_global_state(self, app_id, state):
        self.global_states[app_id] = state
    
    def eval_transactions(self, transactions):
        self.init_ledger_db()
        self.write()
        self.write_transactions(transactions)
        try:
            output = self.run()
        except Exception as e:
            result = e.args[0]
            if 'logic eval error' in result:
                txn_id = re.findall('transaction ([0-9A-Z]+):', result)[0]
                app_id = None
                for stxn in transactions:
                    if stxn.get_txid() == txn_id:
                        app_id = stxn.transaction.index
                        break
                error = re.findall('error: (.+?) pc=', result)[0]
                pc = int(re.findall('pc=(\d+)', result)[0])
                line = None
                if app_id:
                    p = self.apps[app_id]['approval_program']
                    line = p.lookup(pc)
                raise LogicEvalError(result, txn_id, error, line) from None
            elif 'rejected by logic' in result:
                txn_id = re.findall('transaction ([0-9A-Z]+):', result)[0]
                lsig = None
                for stxn in transactions:
                    if stxn.get_txid() == txn_id:
                        lsig = stxn.lsig
                        break
                if 'err=' in result:
                    error = re.findall('err=(.+?) pc=', result)[0]
                    pc = int(re.findall('pc=(\d+)', result)[0])
                else:
                    error = 'reject'
                    pc = None
                line = None
                raise LogicSigReject(result, txn_id, error, line) from None
            else:
                raise
        return output

    def write_transactions(self, transactions):
        write_to_file(transactions, self.stxn_filename)
    
    def init_ledger_db(self):
        return gojig.init_ledger()

    def run(self):
        return gojig.eval()

    def print_accounts(self):
        print(gojig.read())
        self.open_db()
        accounts = self.db.execute('select * from accountbase').fetchall()
        for a in accounts:
            print(a[0], encode_address(a[1]), msgpack.unpackb(a[2]))
        self.db.close()

    def write(self):
        self.open_db()
        self.write_accounts()
        self.write_apps()
        self.write_block()
        self.db.commit()
        self.db.close()

    def write_assets(self):
        for asset_id, a in self.assets.items():
            creator_addrid = self.accounts[a['creator']]['rowid']
            data = {
                'a': a['total'],
                'b': 0,
                'c': False,
                'd': b'TEST',
                'e': b'TEST',
                'f': b'https://example.com',
                'g': b'', # metadatahash
                'h': None,
                'i': None,
                'j': None,
                'k': None,
                'y': 7,
            }
            q = 'INSERT INTO resources (addrid, aidx, data) VALUES (?, ?, ?)'
            self.db.execute(q, [creator_addrid, asset_id, msgpack.packb(data)])
            q = 'INSERT INTO assetcreators (asset, creator, ctype) VALUES (?, ?, ?)'
            self.db.execute(q, [asset_id, decode_address(a['creator']), 0])

    def write_apps(self):
        for app_id, a in self.apps.items():
            creator_addrid = self.accounts[a['creator']]['rowid']
            global_state = self.global_states.get(app_id, {})
            g = {}
            for k,v  in global_state.items():
                g[k] = {}
                if type(v) == bytes:
                    g[k]['tt'] = 1
                    g[k]['tb'] = v
                else:
                    g[k]['tt'] = 2
                    g[k]['ui'] = v
            data = {
                'q': a['approval_program'].bytecode,
                'r': a['approval_program'].bytecode,
                's': g, # global state
                't': a['local_ints'],
                'u': a['local_bytes'],
                'v': a['global_ints'],
                'w': a['global_bytes'],
                'y': 3,
            }
            q = 'INSERT INTO resources (addrid, aidx, data) VALUES (?, ?, ?)'
            self.db.execute(q, [creator_addrid, app_id, msgpack.packb(data)])
            q = 'INSERT INTO assetcreators (asset, creator, ctype) VALUES (?, ?, ?)'
            self.db.execute(q, [app_id, decode_address(a['creator']), 1])

    def write_accounts(self):
        for address, a in self.accounts.items():
            algo = a['balances'][0][0]
            data = {
                'b': algo,
                # 'e': a.get('auth_addr'),
                'j': len(a['balances']) - 1,
                # 'l': len(a['local_states']),
                'k': sum(1 for a in self.apps.values() if a['creator'] == address),
            }
            q = 'INSERT INTO accountbase (address, data) VALUES (?, ?) returning rowid'
            a['rowid'] = self.db.execute(q, [decode_address(address), msgpack.packb(data)]).fetchone()[0]
            for asset_id, b in a['balances'].items():
                if asset_id > 0:
                    data = {
                        'l': b[0], # balance
                        'm': b[1], # frozen
                        'y': 0 if b[0] else 4,
                    }
                    if self.assets[asset_id]['creator'] == address:
                        q = 'INSERT INTO assetcreators (asset, creator, ctype) VALUES (?, ?, ?)'
                        self.db.execute(q, [asset_id, decode_address(address), 0])
                        asset = self.assets[asset_id]
                        data.update({
                            'a': asset.get('total', 0),
                            'b': asset.get('decimals', 0),
                            'c': asset.get('default_frozen', False),
                            'd': asset.get('unit_name', b''),
                            'e': asset.get('name', b''),
                            'f': asset.get('url', b''),
                            'g': asset.get('metadata_hash', b''),
                            'h': asset.get('manager', None),
                            'i': asset.get('reserve', None),
                            'j': asset.get('freeze', None),
                            'k': asset.get('clawback', None),
                            'y': 7,
                        })
                    q = 'INSERT INTO resources (addrid, aidx, data) VALUES (?, ?, ?)'
                    self.db.execute(q, [a['rowid'], asset_id, msgpack.packb(data)])
            
            for app_id, local_state in a['local_states'].items():
                state = {}
                for k,v  in local_state.items():
                    state[k] = {}
                    if type(v) == bytes:
                        state[k]['tt'] = 1
                        state[k]['tb'] = v
                    else:
                        state[k]['tt'] = 2
                        state[k]['ui'] = v
                data = {
                    'n': 16,
                    'o': 16,
                    'p': state, # local_state state
                    'y': 0,
                }
                q = 'INSERT INTO resources (addrid, aidx, data) VALUES (?, ?, ?)'
                self.db.execute(q, [a['rowid'], app_id, msgpack.packb(data)])

        q = "UPDATE acctrounds SET rnd=? WHERE id='acctbase' AND rnd<?"
        self.db.execute(q, [0, 0])

    def write_block(self):
        pass