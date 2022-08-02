import unittest
from algojig.gojig import compile
from algojig.teal import TealProgram


class TestDebug(unittest.TestCase):

    def test_pass_compile(self):
        program, sourcemap = compile(teal='#pragma version 7\nint 1')
        self.assertEqual(program, b'\x07\x81\x01')

    def test_pass_compile_file(self):
        program, sourcemap = compile(filename='/Users/fergal/Dropbox/hipo/algoswap/tinyman-amm-contracts-v2/contracts/build/pool_template.teal')

    def test_pass_compile_program(self):
        p = TealProgram(teal='#pragma version 6\nint 1')
        self.assertEqual(p.hash, 'ZG2RRCHBZ4K2QKP3NGMYVF2MVG7YW2TSNJPVFVLEGX7KGQ46QVPJGOFTK4')
        self.assertEqual(p.bytecode, b'\x06\x81\x01')
