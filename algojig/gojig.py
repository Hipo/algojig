import base64
import importlib.resources
import json
import platform
import subprocess
from io import BytesIO

from algosdk.encoding import msgpack

import algojig

machine = platform.machine()
binary = f'algojig_{machine}'


def run(command, *args, input=None):
    with importlib.resources.files(algojig).joinpath(binary) as p:
        output = subprocess.run([p, command, *args], capture_output=True, input=input)
        return output


def init_ledger(block_timestamp):
    output = run("init", str(block_timestamp))
    # print(output.stderr.decode())
    if output.returncode != 0:
        raise Exception(output.stderr)
    return output


def eval():
    output = run("eval")
    if output.returncode == 0:
        # print(output.stderr.decode())
        outputs = output.stdout
        accounts = []
        boxes = {}
        u = msgpack.Unpacker(BytesIO(outputs), raw=True, strict_map_key=False, use_list=True)
        data = list(u)
        block = data[0]
        # backwards compatibility for gojig binaries that don't output accounts
        if len(data) > 1:
            accounts = data[1]
            boxes = data[2]
        else:
            accounts = {}
        result = {
            'block': block,
            'accounts': accounts,
            'boxes': boxes,
        }
        return result
    else:
        raise Exception(output.stderr.decode())


def read():
    output = run("read")
    if output.returncode == 0:
        return msgpack.unpackb(output.stdout, raw=True, strict_map_key=False)
    else:
        return output.stderr


def compile(filename=None, teal=None):
    if teal is not None:
        if type(teal) == str:
            teal = teal.encode()
        filename = '-'
    output = run("compile", filename, input=teal)
    if output.returncode == 0:
        program, sourcemap = output.stdout.split(b'\n')
        return base64.b64decode(program), json.loads(sourcemap)
    else:
        raise Exception(output.stderr)
