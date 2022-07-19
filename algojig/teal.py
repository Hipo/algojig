from pathlib import Path
from algosdk import source_map, logic
from .gojig import compile

class TealProgram:
    def __init__(self, filename=None, teal=None, bytecode=None):
        self.teal = teal
        self.filename = filename
        if self.filename:
            self.teal = open(filename).read()
        else:
            self.filename = 'input.teal'
        self.bytecode = bytecode
        self.source_map = {}
        self.hash = None
        if self.bytecode is None:
            self.compile()
    
    def compile_teal(self):
        self.bytecode, map = compile(teal=self.teal)
        try:
            self.hash = logic.address(self.bytecode)
        except Exception:
            pass
        self.source_map = source_map.SourceMap(map)

    def compile(self):
        self.compile_teal()

    def lookup(self, pc):
        line = self.source_map.get_line_for_pc(pc)
        src =  self.teal.split('\n')[line].strip()
        result = {
            'filename': self.filename,
            'line_no': line,
            'line': src,
            'pc': pc,
        }
        return result

    def write_files(self, output_path):
        output_path = Path(output_path)
        output_path.mkdir(exist_ok=True)
        base_filename = self.filename.replace('.teal', '')
        with open(output_path / f'{base_filename}.tok', 'wb') as f:
            f.write(self.bytecode)
