import base64
import importlib.resources
import json
import subprocess
import platform
import algojig
from algosdk.encoding import msgpack

machine = platform.machine()
binary = f'algojig_{machine}'

def run(command, *args, input=None):
    with importlib.resources.path(algojig, binary) as p:
        output = subprocess.run([p, command, *args], capture_output=True, input=input)
        return output


def init_ledger():
    output = run("init")
    # print(output.stderr.decode())
    if output.returncode != 0:
        raise Exception(output.stderr)
    return output


def eval():
    output = run("eval")
    if output.returncode == 0:
        # print(output.stderr.decode())
        return msgpack.unpackb(output.stdout, raw=True, strict_map_key=False)
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
