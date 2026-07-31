import unittest

from solution import (
    DivisionByZero,
    EvalError,
    UnbalancedParen,
    UnexpectedChar,
    UnexpectedEnd,
    eval_expr,
)


class TestValues(unittest.TestCase):
    def assertValue(self, expr, expected):
        self.assertAlmostEqual(eval_expr(expr), expected, places=9, msg=f"pour {expr!r}")

    def test_addition(self):
        self.assertValue("1+2", 3.0)

    def test_precedence(self):
        self.assertValue("2+3*4", 14.0)

    def test_subtraction_left_associative(self):
        self.assertValue("10-3-2", 5.0)

    def test_division_left_associative(self):
        self.assertValue("100/5/2", 10.0)

    def test_parentheses(self):
        self.assertValue("(2+3)*4", 20.0)

    def test_nested_parentheses(self):
        self.assertValue("((1+2)*(3+4))", 21.0)

    def test_unary_minus(self):
        self.assertValue("-5+3", -2.0)

    def test_repeated_unary(self):
        self.assertValue("--5", 5.0)

    def test_unary_binds_looser_than_power(self):
        self.assertValue("-2^2", -4.0)

    def test_power_right_associative(self):
        self.assertValue("2^3^2", 512.0)

    def test_unary_exponent(self):
        self.assertValue("2^-1", 0.5)

    def test_decimals(self):
        self.assertValue("1.5*2", 3.0)
        self.assertValue("0.5^2", 0.25)

    def test_python_modulo_semantics(self):
        self.assertValue("7%3", 1.0)
        self.assertValue("-7%3", 2.0)

    def test_whitespace_ignored(self):
        self.assertValue("  1  +  2 * ( 3 - 1 )  ", 5.0)

    def test_product_of_negatives(self):
        self.assertValue("(-3)*(-4)", 12.0)

    def test_returns_float(self):
        self.assertIsInstance(eval_expr("1+1"), float)


class TestErrors(unittest.TestCase):
    def test_empty_input(self):
        with self.assertRaises(UnexpectedEnd):
            eval_expr("")

    def test_trailing_operator(self):
        with self.assertRaises(UnexpectedEnd):
            eval_expr("2+")
        with self.assertRaises(UnexpectedEnd):
            eval_expr("-")

    def test_unknown_character(self):
        with self.assertRaises(UnexpectedChar) as ctx:
            eval_expr("2 & 3")
        self.assertEqual(ctx.exception.char, "&")

    def test_operand_expected(self):
        with self.assertRaises(UnexpectedChar) as ctx:
            eval_expr("1 + * 2")
        self.assertEqual(ctx.exception.char, "*")

    def test_unclosed_paren(self):
        with self.assertRaises(UnbalancedParen):
            eval_expr("(1+2")

    def test_extra_close_paren(self):
        with self.assertRaises(UnbalancedParen):
            eval_expr("1+2)")

    def test_division_by_zero(self):
        with self.assertRaises(DivisionByZero):
            eval_expr("1/0")
        with self.assertRaises(DivisionByZero):
            eval_expr("1%0")

    def test_division_by_zero_only_when_exact(self):
        self.assertAlmostEqual(eval_expr("1/0.5"), 2.0, places=9)

    def test_all_errors_derive_from_eval_error(self):
        for cls in (UnexpectedChar, UnexpectedEnd, UnbalancedParen, DivisionByZero):
            self.assertTrue(issubclass(cls, EvalError), cls.__name__)


if __name__ == "__main__":
    unittest.main()
