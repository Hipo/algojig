import logging
import re
import sqlite3

from algosdk.account import generate_account
from algosdk.encoding import decode_address, encode_address, msgpack
from algosdk.transaction import write_to_file
from algosdk.logic import get_application_address

from . import gojig
from .exceptions import LogicEvalError, LogicSigReject, AppCallReject
from .program import read_program

logger = logging.getLogger(__name__)


class JigLedger:
    def __init__(self):
        self.filename = '/tmp/jig/jig_ledger.sqlite3.tracker.sqlite'
        self.block_db_filename = '/tmp/jig/jig_ledger.sqlite3.block.sqlite'
        self.stxn_filename = '/tmp/jig/stxns'
        self.db = None
        self.block_db = None
        self.apps = {}
        self.boxes = {}
        self.assets = {}
        self.accounts = {}
        self.global_states = {}
        self.raw_accounts = {}
        self.creator_sk, self.creator = generate_account()
        self.set_account_balance(self.creator, 100_000_000)
        self.next_timestamp = 1000

    def set_account_balance(self, address, balance, asset_id=0, frozen=False):
        if address not in self.accounts:
            self.accounts[address] = {'address': address, 'local_states': {}, 'balances': {}}
        if asset_id and asset_id not in self.assets:
            self.create_asset(asset_id)
        self.accounts[address]['balances'][asset_id] = [balance, frozen]

    def get_account_balance(self, address, asset_id=0):
        if address not in self.accounts:
            return [0, False]
        if asset_id not in self.accounts[address]['balances']:
            return [0, False]
        return self.accounts[address]['balances'][asset_id]

    def opt_in_asset(self, address, asset_id):
        assert asset_id, "Opt-in requires an asset id."
        self.set_account_balance(address, 0, asset_id=asset_id)

    def add(self, address, amount, asset_id=0):
        balance, _ = self.accounts[address]['balances'].get(asset_id, [0, False])
        new_balance = balance + amount
        assert new_balance >= 0
        self.set_account_balance(address, new_balance, asset_id=asset_id)

    def subtract(self, address, amount, asset_id=0):
        self.add(address, amount * -1, asset_id)

    def move(self, amount, asset_id=0, sender=None, receiver=None):
        assert sender or receiver

        if receiver:
            self.add(receiver, amount, asset_id)

        if sender:
            self.subtract(sender, amount, asset_id)

    def create_asset(self, asset_id, params=None):
        if asset_id is None:
            caid = 0
            for id in self.apps:
                if id >= caid:
                    caid = id + 1
            for id in self.assets:
                if id >= caid:
                    caid = id + 1
            asset_id = caid
        params = params or {}

        assert asset_id, "Invalid asset id."
        assert asset_id not in self.assets, f"Asset {asset_id} is already exists."

        if 'creator' not in params:
            params['creator'] = self.creator
        if 'total' not in params:
            params['total'] = (2**64 - 1)
        if 'unit_name' not in params:
            params['unit_name'] = 'TEST'

        self.assets[asset_id] = params
        self.set_account_balance(params['creator'], params['total'], asset_id=asset_id)
        return asset_id

    def create_app(self, app_id, approval_filename=None, approval_program=None, creator=None, local_ints=16, local_bytes=16, global_ints=64, global_bytes=64, extra_pages=0):
        if approval_program is None:
            approval_program = read_program(approval_filename)
        self.apps[app_id] = {
            'app_id': app_id,
            'approval_program': approval_program,
            'approval_program_bytecode': approval_program.bytecode,
            'creator': creator or self.creator,
            'local_ints': local_ints,
            'local_bytes': local_bytes,
            'global_ints': global_ints,
            'global_bytes': global_bytes,
            'extra_pages': extra_pages,
        }

    def set_local_state(self, address, app_id, state):
        self.accounts[address]['local_states'][app_id] = state
        if state is None:
            del self.accounts[address]['local_states'][app_id]

    def set_global_state(self, app_id, state):
        self.global_states[app_id] = state

    def update_local_state(self, address, app_id, state_delta):
        self.accounts[address]['local_states'][app_id].update(state_delta)

    def update_global_state(self, app_id, state_delta):
        self.global_states[app_id].update(state_delta)

    def set_box(self, app_id, key, value):
        if type(value) is not bytearray:
            value = bytearray(value)
        if app_id not in self.boxes:
            self.boxes[app_id] = {}
        if key in self.boxes[app_id]:
            # use slicing to mutate the existing object
            self.boxes[app_id][key][:] = value[:]
        else:
            self.boxes[app_id][key] = value

    def set_auth_addr(self, address, auth_addr):
        self.accounts[address]['auth_addr'] = auth_addr

    def get_global_state(self, app_id):
        return self.global_states[app_id]

    def get_local_state(self, address, app_id):
        return self.accounts[address]['local_states'][app_id]

    def get_box(self, app_id, key):
        return self.boxes[app_id][key]

    def box_exists(self, app_id, key):
        return key in self.boxes.get(app_id, {})

    def get_raw_account(self, address):
        return self.raw_accounts.get(address, {})

    def eval_transactions(self, transactions, block_timestamp=None):
        self.init_ledger_db(block_timestamp or self.next_timestamp)
        self.write()
        self.write_transactions(transactions)
        try:
            result = gojig.eval()
        except Exception as e:
            result = e.args[0]
            if 'logic eval error' in result:
                txn_id = re.findall('transaction ([0-9A-Z]+):', result)[0]
                app_id = None
                for stxn in transactions:
                    if stxn.get_txid() == txn_id:
                        app_id = stxn.transaction.index
                        break
                error = re.findall('error: (.+?) pc=', result)[-1]
                pc = int(re.findall(r'pc=(\d+)', result)[-1])
                line = None
                if app_id:
                    p = self.apps[app_id]['approval_program']
                    line = p.lookup(pc)
                if 'logic eval error: logic eval error:' in result:
                    print(result)
                raise LogicEvalError(result, txn_id, error, line) from None
            elif 'rejected by logic' in result:
                txn_id = re.findall('transaction ([0-9A-Z]+):', result)[0]
                # lsig = None
                # for stxn in transactions:
                #     if stxn.get_txid() == txn_id:
                #         lsig = stxn.lsig
                #         break
                if 'err=' in result and 'pc=' in result:
                    error = re.findall('err=(.+?) pc=', result)[0]
                    pc = int(re.findall(r'pc=(\d+)', result)[0])
                else:
                    error = 'reject'
                    pc = None
                line = None
                raise LogicSigReject(result, txn_id, error, line) from None
            elif 'transaction rejected by ApprovalProgram' in result:
                raise AppCallReject(result)
            else:
                raise
        for a in list(result['accounts'].keys()):
            result['accounts'][encode_address(a)] = result['accounts'].pop(a)
        self.update_accounts(result['accounts'])
        self.update_boxes(result['boxes'])
        self.last_block = result['block']
        return result['block']

    def write_transactions(self, transactions):
        write_to_file(transactions, self.stxn_filename)

    def init_ledger_db(self, block_timestamp):
        return gojig.init_ledger(block_timestamp)

    def open_db(self):
        self.db = sqlite3.connect(self.filename)
        self.block_db = sqlite3.connect(self.block_db_filename)

    def write(self):
        self.open_db()
        self.write_accounts()
        self.write_apps()
        self.write_boxes()
        self.write_block()
        self.db.commit()
        self.db.close()
        self.block_db.commit()
        self.block_db.close()

    def write_apps(self):
        for app_id, a in self.apps.items():
            creator_addrid = self.accounts[a['creator']]['rowid']
            global_state = self.global_states.get(app_id, {})
            g = {}
            for k, v in global_state.items():
                g[k] = {}
                if type(v) == bytes:
                    g[k]['tt'] = 1
                    g[k]['tb'] = v
                else:
                    g[k]['tt'] = 2
                    g[k]['ui'] = v
            data = {
                'q': a['approval_program_bytecode'],
                'r': b"\x06\x81\x01",
                's': g,     # global state
                't': a['local_ints'],
                'u': a['local_bytes'],
                'v': a['global_ints'],
                'w': a['global_bytes'],
                'x': a['extra_pages'],
                'y': AppResourceFlag.CREATOR,
            }
            q = 'INSERT INTO resources (addrid, aidx, data) VALUES (?, ?, ?)'
            self.db.execute(q, [creator_addrid, app_id, msgpack.packb(data)])
            q = 'INSERT INTO assetcreators (asset, creator, ctype) VALUES (?, ?, ?)'
            self.db.execute(q, [app_id, decode_address(a['creator']), 1])

    def write_accounts(self):
        for address, a in self.accounts.items():
            algo = a['balances'][0][0]
            for app_id in self.apps:
                if get_application_address(app_id) == address:
                    break
            else:
                app_id = None
            data = {
                'b': algo,
                'e': decode_address(a.get('auth_addr')),
                'j': len(a['balances']) - 1,
                'l': len(a['local_states']),
                'k': sum(1 for a in self.apps.values() if a['creator'] == address),
            }
            # Box related data only applies to application accounts
            if app_id is not None:
                if self.boxes.get(app_id):
                    data['m'] = len(self.boxes[app_id])  # TotalBoxes
                    data['n'] = sum(len(k) + len(v or "") for k, v in self.boxes[app_id].items())  # TotalBoxBytes

            q = 'INSERT INTO accountbase (address, data) VALUES (?, ?)'
            a['rowid'] = self.db.execute(q, [decode_address(address), msgpack.packb(data)]).lastrowid
            for asset_id, b in a['balances'].items():
                if asset_id > 0:
                    data = {
                        'l': b[0],  # balance
                        'm': b[1],  # frozen
                        'y': AssetResourceFlag.HOLDER if (b[0] or b[1]) else AssetResourceFlag.OPTEDIN,
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
                            'h': decode_address(asset['manager']) if 'manager' in asset else None,
                            'i': decode_address(asset['reserve']) if 'reserve' in asset else None,
                            'j': decode_address(asset['freeze']) if 'freeze' in asset else None,
                            'k': decode_address(asset['clawback']) if 'clawback' in asset else None,
                            "y": AssetResourceFlag.CREATOR_AND_HOLDER if (b[0] or b[1]) else AssetResourceFlag.CREATOR,
                        })
                    q = 'INSERT INTO resources (addrid, aidx, data) VALUES (?, ?, ?)'
                    self.db.execute(q, [a['rowid'], asset_id, msgpack.packb(data)])

            for app_id, local_state in a['local_states'].items():
                state = {}
                app = self.apps[app_id]
                for k, v in local_state.items():
                    state[k] = {}
                    if type(v) == bytes:
                        state[k]['tt'] = 1
                        state[k]['tb'] = v
                    else:
                        state[k]['tt'] = 2
                        state[k]['ui'] = v
                data = {
                    'n': app['local_ints'],
                    'o': app['local_bytes'],
                    'p': state,     # local_state state
                    'y': AppResourceFlag.HOLDER if state else AppResourceFlag.OPTEDIN,
                }
                q = 'INSERT INTO resources (addrid, aidx, data) VALUES (?, ?, ?)'
                self.db.execute(q, [a['rowid'], app_id, msgpack.packb(data)])

        q = "UPDATE acctrounds SET rnd=? WHERE id='acctbase' AND rnd<?"
        self.db.execute(q, [0, 0])

    def write_boxes(self):
        q = 'INSERT INTO kvstore (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value'
        for app_id, boxes in self.boxes.items():
            for key, value in boxes.items():
                box_key = (b'bx:' + app_id.to_bytes(8, 'big') + key)
                self.db.execute(q, [box_key, value or ""])

    def write_block(self):
        max_id = max(list(self.assets.keys()) + list(self.apps.keys()) + [-1])
        q = "SELECT hdrdata from blocks where rnd = 1"
        hdr_b = self.block_db.execute(q).fetchone()[0]
        hdr = msgpack.unpackb(hdr_b, strict_map_key=False)
        # Set 'tc' (Transaction Counter) which defines where asset/app_ids start
        # Set it to 1 greater than the current max id used for assets/apps
        hdr['tc'] = max_id + 1
        q = "UPDATE blocks set hdrdata = ? where rnd = 1"
        self.block_db.execute(q, [msgpack.packb(hdr)])

    def update_boxes(self, updated_boxes):
        updated_keys = set()
        for k, v in updated_boxes.items():
            app_id = int.from_bytes(k[3:11], "big")
            key = k[11:]
            updated_keys.add((app_id, key))
            self.set_box(app_id, key, v)
        # Remove deleted boxes:
        for app_id in self.boxes:
            for key in list(self.boxes[app_id].keys()):
                if (app_id, key) not in updated_keys:
                    self.boxes[app_id].pop(key)

    def update_accounts(self, updated_accounts):
        old_assets = dict(self.assets)
        self.raw_accounts = updated_accounts
        for a in updated_accounts:
            # asset param records for asset creators
            for aid, params in updated_accounts[a].get(b'apar', {}).items():
                self.assets[aid] = {
                    'total': params.get(b't', 0),
                    'default_frozen': params.get(b'df', False),
                    'decimals': params.get(b'dc', 0),
                    'unit_name': params.get(b'un', None),
                    'name': params.get(b'an', None),
                    'url': params.get(b'au', None),
                    "manager": encode_address(params.get(b"m", None)),
                    'reserve': encode_address(params.get(b'r', None)),
                    'freeze': encode_address(params.get(b'f', None)),
                    'clawback': encode_address(params.get(b'c', None)),
                    'metadata_hash': params.get(b'am', None),
                    'creator': a,
                }
                # ensure creator has an asset holding record even if it is a 0 amount
                if b'asset' not in updated_accounts[a]:
                    updated_accounts[a][b'asset'] = {}
                if aid not in updated_accounts[a][b'asset']:
                    updated_accounts[a][b'asset'][aid] = {b'a': 0}
            if a not in self.accounts:
                self.set_account_balance(a, 0)
            account = self.accounts[a]
            # reset all account balances
            account['balances'] = {}
            account['balances'][0] = [updated_accounts[a].get(b'algo', 0), False]
            for aid, holding in updated_accounts[a].get(b'asset', {}).items():
                account['balances'][aid] = [holding.get(b'a', 0), holding.get(b'f', False)]

            if b'spend' in updated_accounts[a]:
                account['auth_addr'] = encode_address(updated_accounts[a][b'spend'])

            # opted in apps
            account['local_states'] = {}
            for aid, data in updated_accounts[a].get(b'appl', {}).items():
                state = {}
                for k, v in data.get(b'tkv', {}).items():
                    state[k] = v.get(b'tb') if v[b'tt'] == 1 else v.get(b'ui', 0)
                account['local_states'][aid] = state

            # created apps
            for aid, data in updated_accounts[a].get(b'appp', {}).items():
                if aid not in self.apps:
                    local_schema = data.get(b'lsch', {})
                    global_schema = data.get(b'gsch', {})
                    self.apps[aid] = {
                        'app_id': aid,
                        'creator': a,
                        'approval_program_bytecode': data[b'approv'],
                        'clear_program_bytecode': data[b'clearp'],
                        'local_ints': local_schema.get(b'nui', 0),
                        'local_bytes': local_schema.get(b'nbs', 0),
                        'global_ints': global_schema.get(b'nui', 0),
                        'global_bytes': global_schema.get(b'nbs', 0),
                    }
                state = {}
                for k, v in data.get(b'gs', {}).items():
                    state[k] = v.get(b'tb') if v[b'tt'] == 1 else v.get(b'ui', 0)
                self.global_states[aid] = state

            # TODO: We don't handle changes to the app's programs here.
            # We should be updating self.apps too but that's a bit tricky because it contains references
            # to Programs instead of raw bytecode

        for a in old_assets:
            if a not in self.assets:
                logger.debug(f'Deleted Asset {a}')
        for a in self.assets:
            if a not in old_assets:
                logger.debug(f'New Asset {a}')


# See https://github.com/algorand/go-algorand/blob/d389196e9ccd023216ccaade1b4d93bcc31c2e69/ledger/accountdb.go#L1622
# The use of the resource flags in accountdb.go is massively confusing but here we set the values for the scenarios we expect.
class AssetResourceFlag:
    CREATOR_AND_HOLDER = 2
    CREATOR = 3
    HOLDER = 0
    OPTEDIN = 4


class AppResourceFlag:
    CREATOR_AND_HOLDER = 2
    CREATOR = 3
    HOLDER = 0
    OPTEDIN = 8
