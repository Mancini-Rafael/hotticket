import logging

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

LABEL_WIDTH_PX = 112  # 14mm at 203 DPI


class PrinterConnectionError(Exception):
    pass


class Printer:
    def __init__(self, dry_run: bool = False, density: int = 3) -> None:
        self._dry_run = dry_run
        self._density = density
        self._client = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def connect(self, port: str) -> None:
        """
        Connect to the Niimbot via serial port (USB-C or Bluetooth serial).
        Raises PrinterConnectionError on failure.
        """
        if self._dry_run:
            logger.debug("[DRY RUN] Skipping connection to %s", port)
            return
        try:
            from niimprint import SerialTransport, PrinterClient
            transport = SerialTransport(port)
            self._client = PrinterClient(transport)
            self._client.heartbeat()
            logger.debug("Connected to printer at %s", port)
        except Exception as e:
            raise PrinterConnectionError(f"Could not connect to {port}: {e}") from e

    def print_label(self, text: str) -> None:
        """Render text and send to printer. Errors are logged, not raised."""
        if self._dry_run:
            logger.warning("[DRY RUN] Would print: %s", text)
            return
        try:
            image = self._render(text)
            self._client.print_image(image, density=self._density)
            logger.debug("Printed: %s", text)
        except Exception as e:
            logger.error("Print failed for %r: %s", text, e)

    def discover(self) -> list[dict]:
        """
        List available serial ports that look like Niimbot printers.
        Returns [{name, address}] where address is the port path.
        """
        try:
            return self._discover_serial_ports()
        except Exception as e:
            logger.error("Discovery failed: %s", e)
            return []

    def close(self) -> None:
        """Disconnect from the printer cleanly."""
        if self._client is None:
            return
        try:
            transport = getattr(self._client, "_transport", None)
            if transport is not None and hasattr(transport, "_serial"):
                transport._serial.close()
        except Exception:
            pass
        finally:
            self._client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render(self, text: str) -> Image.Image:
        """Render text to a LABEL_WIDTH_PX-wide monochrome PIL image."""
        font = ImageFont.load_default()
        lines = self._wrap_text(text, font)
        line_height = font.getbbox("A")[3] + 2  # height + 2px padding
        img_height = max(line_height * len(lines), 1)

        image = Image.new("1", (LABEL_WIDTH_PX, img_height), color=1)
        draw = ImageDraw.Draw(image)

        y = 0
        for line in lines:
            draw.text((0, y), line, font=font, fill=0)
            y += line_height

        return image

    def _wrap_text(self, text: str, font: ImageFont.ImageFont) -> list[str]:
        """Word-wrap text to fit within LABEL_WIDTH_PX. Char-breaks long words."""
        words = text.split()
        lines: list[str] = []
        current = ""

        for word in words:
            candidate = f"{current} {word}".strip() if current else word
            if self._text_width(candidate, font) <= LABEL_WIDTH_PX:
                current = candidate
            else:
                if current:
                    lines.append(current)
                if self._text_width(word, font) > LABEL_WIDTH_PX:
                    for fragment in self._char_break(word, font):
                        lines.append(fragment)
                    current = ""
                else:
                    current = word

        if current:
            lines.append(current)

        return lines or [""]

    def _char_break(self, word: str, font: ImageFont.ImageFont) -> list[str]:
        """Break a single word that exceeds label width into character-level chunks."""
        fragments: list[str] = []
        current = ""
        for char in word:
            candidate = current + char
            if self._text_width(candidate, font) <= LABEL_WIDTH_PX:
                current = candidate
            else:
                if current:
                    fragments.append(current)
                current = char
        if current:
            fragments.append(current)
        return fragments

    @staticmethod
    def _text_width(text: str, font: ImageFont.ImageFont) -> int:
        """Return pixel width of text using ImageDraw.textlength (Pillow >= 9.2)."""
        scratch = Image.new("1", (1, 1))
        draw = ImageDraw.Draw(scratch)
        return int(draw.textlength(text, font=font))

    @staticmethod
    def _discover_serial_ports() -> list[dict]:
        """List serial ports, highlighting likely Niimbot candidates."""
        from serial.tools.list_ports import comports
        devices = []
        for port, desc, hwid in comports():
            devices.append({"name": desc or hwid, "address": port})
        return devices
