from django.test import SimpleTestCase
from math import isclose
from .utils import rolling_average, CENTER, LEFT, RIGHT


class RollingAverageTests(SimpleTestCase):
    def assertListAlmostEqual(self, a, b, places=7):
        self.assertEqual(len(a), len(b))
        for x, y in zip(a, b):
            if x is None or y is None:
                self.assertIsNone(x)
                self.assertIsNone(y)
            else:
                self.assertTrue(isclose(x, y, rel_tol=10**-places))

    def test_center_alignment(self):
        data = [1, 2, 3, 4, 5]
        window = 3
        expected = [None, 2.0, 3.0, 4.0, None]
        self.assertListAlmostEqual(
            rolling_average(data, window, alignment=CENTER), expected
        )

    def test_left_alignment(self):
        data = [1, 2, 3, 4, 5]
        window = 3
        expected = [2.0, 3.0, 4.0, None, None]
        self.assertListAlmostEqual(
            rolling_average(data, window, alignment=LEFT), expected
        )

    def test_right_alignment(self):
        data = [1, 2, 3, 4, 5]
        window = 3
        expected = [None, None, 2.0, 3.0, 4.0]
        self.assertListAlmostEqual(
            rolling_average(data, window, alignment=RIGHT), expected
        )

    def test_window_equals_one(self):
        data = [10, 20, 30]
        window = 1
        expected = [10, 20, 30]
        self.assertListAlmostEqual(rolling_average(data, window), expected)

    def test_invalid_alignment_raises(self):
        with self.assertRaises(Exception):
            rolling_average([1, 2, 3], window=2, alignment="diagonal")

    def test_none_padding(self):
        data = [None, 1, 2, 3, 4, 5, None, 5, 4, 3, 2, 1, None]
        window = 3
        expected = [None, None, 2.0, 3.0, 4.0, None, None, None, 4.0, 3.0, 2.0, None, None]
        self.assertListAlmostEqual(rolling_average(data, window), expected)
