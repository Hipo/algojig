
class AppCallReject(Exception):
    def __init__(self, result) -> None:
        self.message = 'AppCall Reject'
        self.result = result
        self.reason = result

    def __str__(self) -> str:
        return self.reason


class LogicEvalError(Exception):
    def __init__(self, result, txn_id, error, source) -> None:
        self.message = 'Logic Eval Error'
        self.txn_id = txn_id
        self.error = error
        self.source = source
        super().__init__(result)

    def __str__(self) -> str:
        line = self.source['line']
        line_no = self.source['line_no']
        return f'{self.error}: L{line_no}: {line}'


class LogicSigReject(Exception):
    def __init__(self, result, txn_id, error, source) -> None:
        self.message = 'LogicSig Reject'
        self.txn_id = txn_id
        self.error = error
        self.source = source
        super().__init__(result)

    def __str__(self) -> str:
        return f'{self.error}'
