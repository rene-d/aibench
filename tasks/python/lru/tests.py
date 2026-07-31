import unittest

from solution import LRUCache


class TestLRUCache(unittest.TestCase):
    def test_leetcode_146_example(self):
        c = LRUCache(2)
        c.put(1, 1)
        c.put(2, 2)
        self.assertEqual(c.get(1), 1)
        c.put(3, 3)
        self.assertIsNone(c.get(2))
        c.put(4, 4)
        self.assertIsNone(c.get(1))
        self.assertEqual(c.get(3), 3)
        self.assertEqual(c.get(4), 4)

    def test_miss_on_empty_cache(self):
        c = LRUCache(2)
        self.assertIsNone(c.get(42))
        self.assertEqual(len(c), 0)

    def test_update_does_not_grow(self):
        c = LRUCache(2)
        c.put(1, 1)
        c.put(1, 10)
        self.assertEqual(len(c), 1)
        self.assertEqual(c.get(1), 10)

    def test_update_refreshes_recency(self):
        c = LRUCache(2)
        c.put(1, 1)
        c.put(2, 2)
        c.put(1, 100)
        c.put(3, 3)
        self.assertIsNone(c.get(2))
        self.assertEqual(c.get(1), 100)
        self.assertEqual(c.get(3), 3)

    def test_get_refreshes_recency(self):
        c = LRUCache(3)
        c.put(1, 1)
        c.put(2, 2)
        c.put(3, 3)
        self.assertEqual(c.get(1), 1)
        c.put(4, 4)
        self.assertIsNone(c.get(2))
        self.assertEqual(c.get(1), 1)
        self.assertEqual(c.get(3), 3)
        self.assertEqual(c.get(4), 4)

    def test_missing_get_has_no_side_effect(self):
        c = LRUCache(2)
        c.put(1, 1)
        c.put(2, 2)
        self.assertIsNone(c.get(99))
        c.put(3, 3)
        self.assertIsNone(c.get(1))
        self.assertEqual(c.get(2), 2)

    def test_capacity_one(self):
        c = LRUCache(1)
        c.put(1, 1)
        c.put(2, 2)
        self.assertIsNone(c.get(1))
        self.assertEqual(c.get(2), 2)
        self.assertEqual(len(c), 1)

    def test_len_never_exceeds_capacity(self):
        c = LRUCache(3)
        for i in range(50):
            c.put(i, i * 2)
            self.assertLessEqual(len(c), 3)
        self.assertEqual(len(c), 3)
        self.assertEqual(c.get(49), 98)
        self.assertEqual(c.get(48), 96)
        self.assertEqual(c.get(47), 94)
        self.assertIsNone(c.get(46))

    def test_zero_value_is_not_a_miss(self):
        c = LRUCache(2)
        c.put(7, 0)
        self.assertEqual(c.get(7), 0)
        self.assertIsNotNone(c.get(7))

    def test_negative_keys_and_values(self):
        c = LRUCache(2)
        c.put(-1, -100)
        c.put(-2, 0)
        self.assertEqual(c.get(-1), -100)
        self.assertEqual(c.get(-2), 0)

    def test_stress_keeps_hot_key(self):
        c = LRUCache(2)
        c.put(0, 0)
        for i in range(1, 20):
            self.assertEqual(c.get(0), 0)
            c.put(i, i)
        self.assertEqual(c.get(0), 0)
        self.assertEqual(c.get(19), 19)
        self.assertIsNone(c.get(18))


if __name__ == "__main__":
    unittest.main()
