import unittest

from pyimmutable import ImmutableDict, ImmutableList

from pykzee.common import Undefined, sanitize


class TestUndefined(unittest.TestCase):
    def test_unique(self):
        u1 = Undefined
        u2 = type(Undefined)()

        self.assertTrue(u1 is u2)

    def test_is_false(self):
        self.assertFalse(bool(Undefined))


class TestSanitize(unittest.TestCase):
    def test_simple(self):
        self.assertTrue(sanitize(ImmutableDict()) is ImmutableDict())
        self.assertTrue(sanitize({}) is ImmutableDict())
        self.assertTrue(sanitize(ImmutableList()) is ImmutableList())
        self.assertTrue(sanitize([]) is ImmutableList())

        self.assertTrue(sanitize(None) is None)
        self.assertTrue(sanitize(True) is True)
        self.assertTrue(sanitize(False) is False)
        self.assertEqual(sanitize("foobar"), "foobar")
        self.assertEqual(sanitize(1234), 1234)
        self.assertEqual(sanitize(1.234), 1.234)

    def test_nested(self):
        self.assertTrue(
            sanitize(
                {
                    "a": 1,
                    "b": None,
                    "c": {"x": True},
                    "d": ImmutableDict(y=False),
                }
            )
            is ImmutableDict(
                a=1, b=None, c=ImmutableDict(x=True), d=ImmutableDict(y=False)
            )
        )

        self.assertTrue(
            sanitize([1, None, [True], ImmutableList([False])])
            is ImmutableList(
                [1, None, ImmutableList([True]), ImmutableList([False])]
            )
        )

    def test_pass_immutable(self):
        self.assertTrue(
            sanitize([[]])
            is sanitize(ImmutableList([[]]))
            is sanitize(ImmutableList([ImmutableList()]))
            is ImmutableList([ImmutableList()])
        )

        self.assertTrue(
            sanitize({"a": {}})
            is sanitize(ImmutableDict({"a": {}}))
            is sanitize(ImmutableDict(a={}))
            is sanitize(ImmutableDict(a=ImmutableDict()))
            is ImmutableDict(a=ImmutableDict())
        )


if __name__ == "__main__":
    unittest.main()
