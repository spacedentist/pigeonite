import unittest

from pyimmutable import ImmutableDict, ImmutableList

from pykzee import AttachedInfo
from pykzee.common import sanitize


# class TestGetSubtree(unittest.TestCase):


class TestResolved(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(immutables_count(), 0)
        data = sanitize(
            {
                "foo": "bar",
                "x1": [0, 1, 2, {"__symlink__": "x2"}, 4],
                "x2": {
                    "y1": 123,
                    "y2": {"__symlink__": "foo"},
                    "y3": {"__symlink__": "/x1/[3]/y1"},
                    "y4": {"__symlink__": ["x2", "y2"]},
                },
            }
        )
        data_resolved = sanitize(
            {
                "foo": "bar",
                "x1": [
                    0,
                    1,
                    2,
                    {"y1": 123, "y2": "bar", "y3": 123, "y4": "bar"},
                    4,
                ],
                "x2": {"y1": 123, "y2": "bar", "y3": 123, "y4": "bar"},
            }
        )
        self.assertEqual(immutables_count(), 11)
        resolved = AttachedInfo.resolved(data)
        self.assertTrue(resolved is data_resolved)
        self.assertEqual(immutables_count(), 24)
        data_resolved = resolved = None
        self.assertEqual(immutables_count(), 24)
        data = None
        self.assertEqual(immutables_count(), 0)


def immutables_count():
    return (
        ImmutableDict._get_instance_count()
        + ImmutableList._get_instance_count()
    )


if __name__ == "__main__":
    unittest.main()
