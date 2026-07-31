import unittest

from solution import top_k

PANGRAM = "the quick brown fox jumps over the lazy dog the fox"


class TestTopK(unittest.TestCase):
    def test_basic_top_three(self):
        self.assertEqual(top_k(PANGRAM, 3), [("the", 3), ("fox", 2), ("brown", 1)])

    def test_ties_sorted_lexicographically(self):
        self.assertEqual(
            top_k(PANGRAM, 6),
            [("the", 3), ("fox", 2), ("brown", 1), ("dog", 1), ("jumps", 1), ("lazy", 1)],
        )

    def test_k_larger_than_vocabulary(self):
        self.assertEqual(top_k("a b a", 100), [("a", 2), ("b", 1)])

    def test_k_zero(self):
        self.assertEqual(top_k(PANGRAM, 0), [])

    def test_empty_text(self):
        self.assertEqual(top_k("", 3), [])

    def test_punctuation_only(self):
        self.assertEqual(top_k("!!! ... ,;:", 3), [])

    def test_case_folded(self):
        self.assertEqual(top_k("Hello, hello! HELLO?", 5), [("hello", 3)])

    def test_digits_are_part_of_words(self):
        self.assertEqual(top_k("a1 a1 b2", 5), [("a1", 2), ("b2", 1)])

    def test_punctuation_splits_words(self):
        self.assertEqual(top_k("rust-lang rust lang", 3), [("lang", 2), ("rust", 2)])

    def test_unicode_lowercasing(self):
        self.assertEqual(top_k("Élan élan ÉLAN naïve", 2), [("élan", 3), ("naïve", 1)])

    def test_returns_tuples(self):
        result = top_k("a a b", 2)
        self.assertTrue(all(isinstance(item, tuple) for item in result))


if __name__ == "__main__":
    unittest.main()
