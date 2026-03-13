import pytest
from PIL import Image
from printer import Printer, LABEL_WIDTH_PX


class TestRenderLabel:
    """Tests for the internal _render(text) -> Image method of Printer."""

    def setup_method(self):
        self.printer = Printer(dry_run=True)

    def test_image_width_equals_label_width(self):
        img = self.printer._render("Buy milk")
        assert img.width == LABEL_WIDTH_PX

    def test_image_height_is_positive(self):
        img = self.printer._render("Buy milk")
        assert img.height > 0

    def test_image_mode_is_monochrome(self):
        img = self.printer._render("Buy milk")
        assert img.mode == "1"

    def test_long_line_wraps_and_increases_height(self):
        short_img = self.printer._render("Hi")
        long_img = self.printer._render(
            "This is a very long task description that should definitely wrap onto multiple lines"
        )
        assert long_img.height > short_img.height

    def test_single_very_long_word_does_not_crash(self):
        # A word longer than LABEL_WIDTH_PX triggers character-level breaking
        long_word = "A" * 200
        img = self.printer._render(long_word)
        assert img.width == LABEL_WIDTH_PX
        assert img.height > 0
