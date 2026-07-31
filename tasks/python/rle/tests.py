import unittest

from solution import decode, encode

LONG = "WWWWWWWWWWWWBWWWWWWWWWWWWBBBWWWWWWWWWWWWWWWWWWWWWWWWB"


class TestEncode(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(encode(""), "")

    def test_single_characters(self):
        self.assertEqual(encode("XYZ"), "XYZ")

    def test_simple_runs(self):
        self.assertEqual(encode("AABBBCCCC"), "2A3B4C")

    def test_with_whitespace(self):
        self.assertEqual(encode("  hsqq qww  "), "2 hs2q q2w2 ")

    def test_multi_digit_counts(self):
        self.assertEqual(encode(LONG), "12WB12W3B24WB")

    def test_case_is_significant(self):
        self.assertEqual(encode("aaAA"), "2a2A")


class TestDecode(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(decode(""), "")

    def test_single_characters(self):
        self.assertEqual(decode("XYZ"), "XYZ")

    def test_simple_runs(self):
        self.assertEqual(decode("2A3B4C"), "AABBBCCCC")

    def test_with_whitespace(self):
        self.assertEqual(decode("2 hs2q q2w2 "), "  hsqq qww  ")

    def test_multi_digit_counts(self):
        self.assertEqual(decode("12WB12W3B24WB"), LONG)


class TestRoundTrip(unittest.TestCase):
    def test_round_trip(self):
        for sample in ["", "XYZ", "AABBBCCCC", "  hsqq qww  ", "zzz ZZ  zZ", LONG]:
            self.assertEqual(decode(encode(sample)), sample)


if __name__ == "__main__":
    unittest.main()
