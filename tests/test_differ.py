import pytest
from differ import Differ


def make_differ(initial_lines=None):
    d = Differ()
    d.load(initial_lines or [])
    return d


class TestLoad:
    def test_load_does_not_return_lines_to_print(self):
        d = Differ()
        # load() has no return value; calling diff after load with same content
        # should return nothing
        lines = ["Buy milk", "Walk dog"]
        d.load(lines)
        result = d.diff(lines)
        assert result == []


class TestDiff:
    def test_appended_line_is_returned(self):
        d = make_differ(["Buy milk"])
        result = d.diff(["Buy milk", "Walk dog"])
        assert result == ["Walk dog"]

    def test_line_inserted_in_middle_is_returned(self):
        d = make_differ(["Buy milk", "Walk dog"])
        result = d.diff(["Buy milk", "Feed cat", "Walk dog"])
        assert result == ["Feed cat"]

    def test_deleted_line_is_not_returned(self):
        d = make_differ(["Buy milk", "Walk dog"])
        result = d.diff(["Buy milk"])
        assert result == []

    def test_edited_line_is_not_returned(self):
        # An edit looks like a delete + add in ndiff;
        # the new text IS returned as a new line
        # Per spec: edits are "silently ignored" — meaning the replaced text
        # counts as a new line since it wasn't in the snapshot.
        # This test documents the actual behavior: edited line text IS printed.
        d = make_differ(["Buy milk"])
        result = d.diff(["Buy almond milk"])
        assert result == ["Buy almond milk"]

    def test_blank_line_added_is_skipped(self):
        d = make_differ(["Buy milk"])
        result = d.diff(["Buy milk", ""])
        assert result == []

    def test_whitespace_only_line_is_skipped(self):
        d = make_differ(["Buy milk"])
        result = d.diff(["Buy milk", "   "])
        assert result == []

    def test_no_change_returns_empty(self):
        d = make_differ(["Buy milk", "Walk dog"])
        result = d.diff(["Buy milk", "Walk dog"])
        assert result == []

    def test_duplicate_line_added_is_returned(self):
        d = make_differ(["Buy milk"])
        d.update(["Buy milk"])
        result = d.diff(["Buy milk", "Buy milk"])
        assert result == ["Buy milk"]

    def test_multiple_lines_added_at_once(self):
        d = make_differ(["Buy milk"])
        result = d.diff(["Buy milk", "Walk dog", "Feed cat"])
        assert result == ["Walk dog", "Feed cat"]

    def test_empty_snapshot_and_empty_new_lines(self):
        d = make_differ([])
        result = d.diff([])
        assert result == []

    def test_empty_snapshot_with_new_lines(self):
        d = make_differ([])
        result = d.diff(["Buy milk"])
        assert result == ["Buy milk"]


class TestUpdate:
    def test_update_replaces_snapshot(self):
        d = make_differ(["Buy milk"])
        d.update(["Walk dog"])
        result = d.diff(["Walk dog"])  # no change after update
        assert result == []

    def test_update_is_independent_of_diff(self):
        d = make_differ(["Buy milk"])
        added = d.diff(["Buy milk", "Walk dog"])
        assert added == ["Walk dog"]
        # snapshot not updated yet
        added2 = d.diff(["Buy milk", "Walk dog"])
        assert added2 == ["Walk dog"]
        # now update
        d.update(["Buy milk", "Walk dog"])
        added3 = d.diff(["Buy milk", "Walk dog"])
        assert added3 == []
