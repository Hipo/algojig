import json
from pathlib import Path
from .teal import TealProgram


class TealishProgram:
    def __init__(self, filename=None, bytecode=None, tealish=None):
        self.filename = filename
        self.tealish_source = tealish
        if self.filename:
            self.tealish_source = open(filename).read()
        self.tealish_source_lines = self.tealish_source.split('\n')
        self.bytecode = bytecode
        self.source_map = {}
        self.teal_program = None
        if self.bytecode is None:
            self.compile()

    def compile(self):
        from tealish import compile_program
        self.teal, self.source_map = compile_program(self.tealish_source)
        self.teal_program = TealProgram(teal='\n'.join(self.teal))
        self.bytecode = self.teal_program.bytecode
        self.source_map.update_from_teal_sourcemap(self.teal_program.source_map)

    def lookup(self, pc):
        teal_src = None
        line = self.source_map.get_tealish_line_for_pc(pc)
        src = self.tealish_source_lines[line - 1].strip()
        result = {
            'filename': self.filename,
            'line_no': line,
            'line': src,
            'pc': pc,
            'teal': teal_src,
        }
        return result

    def write_files(self, output_path):
        output_path = Path(output_path)
        output_path.mkdir(exist_ok=True)
        base_filename = self.filename.replace('.tl', '')
        with open(output_path / f'{base_filename}.teal', 'w') as f:
            f.write('\n'.join(self.teal))
        with open(output_path / f'{base_filename}.map.json', 'w') as f:
            f.write(json.dumps(self.source_map).replace('],', '],\n'))
        self.teal_program.write_files(output_path)
