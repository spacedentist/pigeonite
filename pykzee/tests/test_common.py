import unittest

from pykzee.common import Undefined


class TestUndefined(unittest.TestCase):
    def test_unique(self):
        u1 = Undefined
        u2 = type(Undefined)()

        self.assertTrue(u1 is u2)

    def test_is_false(self):
        self.assertFalse(bool(Undefined))


if __name__ == "__main__":
    unittest.main()
