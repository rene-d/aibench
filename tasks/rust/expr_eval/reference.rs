#[derive(Debug, PartialEq)]
pub enum EvalError {
    UnexpectedChar(char),
    UnexpectedEnd,
    UnbalancedParen,
    DivisionByZero,
}

#[derive(Debug, Clone, Copy, PartialEq)]
enum Tok {
    Num(f64),
    Op(char),
}

impl Tok {
    fn ch(self) -> char {
        match self {
            Tok::Op(c) => c,
            Tok::Num(_) => '0',
        }
    }
}

fn lex(input: &str) -> Result<Vec<Tok>, EvalError> {
    let chars: Vec<char> = input.chars().collect();
    let mut out = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        let c = chars[i];
        if c == ' ' || c == '\t' {
            i += 1;
        } else if c.is_ascii_digit() {
            let start = i;
            while i < chars.len() && chars[i].is_ascii_digit() {
                i += 1;
            }
            if i + 1 < chars.len() && chars[i] == '.' && chars[i + 1].is_ascii_digit() {
                i += 1;
                while i < chars.len() && chars[i].is_ascii_digit() {
                    i += 1;
                }
            }
            let text: String = chars[start..i].iter().collect();
            out.push(Tok::Num(text.parse().unwrap()));
        } else if "+-*/%^()".contains(c) {
            out.push(Tok::Op(c));
            i += 1;
        } else {
            return Err(EvalError::UnexpectedChar(c));
        }
    }
    Ok(out)
}

struct Parser {
    toks: Vec<Tok>,
    pos: usize,
}

impl Parser {
    fn peek(&self) -> Option<Tok> {
        self.toks.get(self.pos).copied()
    }

    fn eat_op(&mut self, ops: &[char]) -> Option<char> {
        if let Some(Tok::Op(c)) = self.peek() {
            if ops.contains(&c) {
                self.pos += 1;
                return Some(c);
            }
        }
        None
    }

    fn expr(&mut self) -> Result<f64, EvalError> {
        let mut acc = self.term()?;
        while let Some(op) = self.eat_op(&['+', '-']) {
            let rhs = self.term()?;
            acc = if op == '+' { acc + rhs } else { acc - rhs };
        }
        Ok(acc)
    }

    fn term(&mut self) -> Result<f64, EvalError> {
        let mut acc = self.unary()?;
        while let Some(op) = self.eat_op(&['*', '/', '%']) {
            let rhs = self.unary()?;
            if rhs == 0.0 && (op == '/' || op == '%') {
                return Err(EvalError::DivisionByZero);
            }
            acc = match op {
                '*' => acc * rhs,
                '/' => acc / rhs,
                _ => acc % rhs,
            };
        }
        Ok(acc)
    }

    fn unary(&mut self) -> Result<f64, EvalError> {
        if self.eat_op(&['-']).is_some() {
            return Ok(-self.unary()?);
        }
        self.power()
    }

    fn power(&mut self) -> Result<f64, EvalError> {
        let base = self.atom()?;
        if self.eat_op(&['^']).is_some() {
            let exp = self.unary()?;
            return Ok(base.powf(exp));
        }
        Ok(base)
    }

    fn atom(&mut self) -> Result<f64, EvalError> {
        match self.peek() {
            None => Err(EvalError::UnexpectedEnd),
            Some(Tok::Num(v)) => {
                self.pos += 1;
                Ok(v)
            }
            Some(Tok::Op('(')) => {
                self.pos += 1;
                let v = self.expr()?;
                match self.peek() {
                    Some(Tok::Op(')')) => {
                        self.pos += 1;
                        Ok(v)
                    }
                    None => Err(EvalError::UnbalancedParen),
                    Some(t) => Err(EvalError::UnexpectedChar(t.ch())),
                }
            }
            Some(t) => Err(EvalError::UnexpectedChar(t.ch())),
        }
    }
}

pub fn eval(expr: &str) -> Result<f64, EvalError> {
    let toks = lex(expr)?;
    let mut p = Parser { toks, pos: 0 };
    let value = p.expr()?;
    match p.peek() {
        None => Ok(value),
        Some(Tok::Op(')')) => Err(EvalError::UnbalancedParen),
        Some(t) => Err(EvalError::UnexpectedChar(t.ch())),
    }
}
