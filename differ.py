import difflib


class Differ:
    def __init__(self) -> None:
        self._snapshot: list[str] = []

    def load(self, lines: list[str]) -> None:
        """Initialize snapshot from existing file content. Nothing is printed."""
        self._snapshot = list(lines)

    def diff(self, new_lines: list[str]) -> list[str]:
        """
        Return lines present in new_lines but not in the current snapshot,
        using difflib.ndiff. Blank/whitespace-only lines are excluded.
        Does NOT update the snapshot.
        """
        result = []
        for line in difflib.ndiff(self._snapshot, new_lines):
            if line.startswith("+ "):
                text = line[2:]
                if text.strip():
                    result.append(text)
        return result

    def update(self, lines: list[str]) -> None:
        """Replace the snapshot with new content."""
        self._snapshot = list(lines)
