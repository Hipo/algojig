
class Program:
    def __init__(self, filename, bytecode=None, algod=None):
        pass

    def compile(self):
        pass


def read_program(filename, algod):
    from .teal import TealProgram
    from .tealish import TealishProgram
    if filename.endswith('.tealish'):
        return TealishProgram(filename=filename, algod=algod)
    elif filename.endswith('.teal'):
        return TealProgram(filename=filename, algod=algod)
    else:
        raise NotImplementedError()
