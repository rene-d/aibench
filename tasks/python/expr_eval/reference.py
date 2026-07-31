class EvalError(Exception):
    pass


class UnexpectedChar(EvalError):
    def __init__(self, char: str) -> None:
        super().__init__(f"caractère inattendu : {char!r}")
        self.char = char


class UnexpectedEnd(EvalError):
    pass


class UnbalancedParen(EvalError):
    pass


class DivisionByZero(EvalError):
    pass


OPERATORS = "+-*/%^()"


def _lex(text: str) -> list[tuple[str, object]]:
    toks: list[tuple[str, object]] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in " \t":
            i += 1
        elif ch.isdigit():
            start = i
            while i < len(text) and text[i].isdigit():
                i += 1
            if i + 1 < len(text) and text[i] == "." and text[i + 1].isdigit():
                i += 1
                while i < len(text) and text[i].isdigit():
                    i += 1
            toks.append(("num", float(text[start:i])))
        elif ch in OPERATORS:
            toks.append(("op", ch))
            i += 1
        else:
            raise UnexpectedChar(ch)
    return toks


class _Parser:
    def __init__(self, toks):
        self.toks = toks
        self.pos = 0

    def peek(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else None

    def eat(self, ops):
        tok = self.peek()
        if tok is not None and tok[0] == "op" and tok[1] in ops:
            self.pos += 1
            return tok[1]
        return None

    def expr(self) -> float:
        acc = self.term()
        while (op := self.eat("+-")) is not None:
            rhs = self.term()
            acc = acc + rhs if op == "+" else acc - rhs
        return acc

    def term(self) -> float:
        acc = self.unary()
        while (op := self.eat("*/%")) is not None:
            rhs = self.unary()
            if op in "/%" and rhs == 0.0:
                raise DivisionByZero()
            if op == "*":
                acc = acc * rhs
            elif op == "/":
                acc = acc / rhs
            else:
                acc = acc % rhs
        return acc

    def unary(self) -> float:
        if self.eat("-") is not None:
            return -self.unary()
        return self.power()

    def power(self) -> float:
        base = self.atom()
        if self.eat("^") is not None:
            return base ** self.unary()
        return base

    def atom(self) -> float:
        tok = self.peek()
        if tok is None:
            raise UnexpectedEnd()
        if tok[0] == "num":
            self.pos += 1
            return tok[1]
        if tok[1] == "(":
            self.pos += 1
            value = self.expr()
            nxt = self.peek()
            if nxt is None:
                raise UnbalancedParen()
            if nxt[0] == "op" and nxt[1] == ")":
                self.pos += 1
                return value
            raise UnexpectedChar(nxt[1] if nxt[0] == "op" else str(nxt[1]))
        raise UnexpectedChar(tok[1])


def eval_expr(expr: str) -> float:
    parser = _Parser(_lex(expr))
    value = parser.expr()
    leftover = parser.peek()
    if leftover is None:
        return float(value)
    if leftover[0] == "op" and leftover[1] == ")":
        raise UnbalancedParen()
    raise UnexpectedChar(leftover[1] if leftover[0] == "op" else str(leftover[1]))
