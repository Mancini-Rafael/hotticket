import logging
import time

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# --- Paper configuration ---
# Change these to match your label stock; pixel dimensions are derived automatically.
DPI = 203
PAPER_WIDTH_MM  = 30
PAPER_HEIGHT_MM = 20

PAPER_WIDTH_PX  = round(PAPER_WIDTH_MM  * DPI / 25.4)  # ~240px
PAPER_HEIGHT_PX = round(PAPER_HEIGHT_MM * DPI / 25.4)  # ~160px

FONT_SIZE = 24


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
        from niimprint import SerialTransport, PrinterClient
        last_error: Exception | None = None
        for attempt in range(1, 3):
            transport = None
            try:
                logger.info("Connecting to %s (attempt %d/4)...", port, attempt)
                transport = SerialTransport(port)
                time.sleep(2)  # Wait for RFCOMM channel to fully establish
                self._client = PrinterClient(transport)
                self._client.heartbeat()
                logger.info("Connected to printer at %s", port)
                return
            except Exception as e:
                last_error = e
                logger.warning("Attempt %d/2 failed: %s", attempt, e)
                if transport is not None and hasattr(transport, "_serial"):
                    try:
                        transport._serial.close()
                    except Exception:
                        pass
                self._client = None
                if attempt < 2:
                    logger.info("Retrying in 3s...")
                    time.sleep(3)
        raise PrinterConnectionError(f"Could not connect to {port}: {last_error}") from last_error

    def print_label(self, text: str) -> None:
        """Render text and send to printer. Errors are logged, not raised."""
        if self._dry_run:
            logger.warning("[DRY RUN] Would print: %s", text)
            return
        try:
            logger.info("Printing: %s", text)
            image = self._render(text)
            self._client.print_image(image, density=self._density)
            logger.info("Done: %s", text)
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
        """Render text centered on a PAPER_WIDTH_PX × PAPER_HEIGHT_PX monochrome image."""
        font = self._load_font(FONT_SIZE)
        lines = self._wrap_text(text, font)
        line_height = font.getbbox("A")[3] + 2  # height + 2px padding
        text_block_height = line_height * len(lines)

        image = Image.new("1", (PAPER_WIDTH_PX, PAPER_HEIGHT_PX), color=1)
        draw = ImageDraw.Draw(image)

        y = max((PAPER_HEIGHT_PX - text_block_height) // 2, 0)
        for line in lines:
            line_width = self._text_width(line, font)
            x = max((PAPER_WIDTH_PX - line_width) // 2, 0)
            draw.text((x, y), line, font=font, fill=0)
            y += line_height

        return image

    @staticmethod
    def _load_font(size: int) -> ImageFont.FreeTypeFont:
        """Load a TrueType font at the given pixel size, falling back to system Helvetica."""
        candidates = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
        for path in candidates:
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                continue
        # Last resort: Pillow's built-in default (bitmap, ignores size)
        logger.warning("No TrueType font found; falling back to default bitmap font")
        return ImageFont.load_default()

    def _wrap_text(self, text: str, font: ImageFont.ImageFont) -> list[str]:
        """Word-wrap text to fit within PAPER_WIDTH_PX. Char-breaks long words."""
        words = text.split()
        lines: list[str] = []
        current = ""

        for word in words:
            candidate = f"{current} {word}".strip() if current else word
            if self._text_width(candidate, font) <= PAPER_WIDTH_PX:
                current = candidate
            else:
                if current:
                    lines.append(current)
                if self._text_width(word, font) > PAPER_WIDTH_PX:
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
            if self._text_width(candidate, font) <= PAPER_WIDTH_PX:
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
        """List serial ports, flagging likely Niimbot candidates."""
        from serial.tools.list_ports import comports
        NIIMBOT_PREFIXES = ("B1", "B21", "B3S", "D11", "D110", "D101")
        devices = []
        for port, desc, hwid in comports():
            port_name = port.split("/")[-1]
            is_niimbot = any(port_name.upper().startswith(p) for p in NIIMBOT_PREFIXES)
            devices.append({
                "name": desc or hwid or port_name,
                "address": port,
                "niimbot": is_niimbot,
            })
        return devices

    @staticmethod
    def scan_niimbot_devices(inquiry_seconds: int = 5) -> list[dict]:
        """
        Scan for Niimbot printers via blueutil.
        Checks paired/connected devices first, then does a live inquiry scan
        for nearby devices. Returns [{name, mac, port, connected}].
        """
        import subprocess, json

        def run_blueutil(*args) -> list[dict]:
            result = subprocess.run(
                ["blueutil", "--format", "json", *args],
                capture_output=True, text=True, timeout=inquiry_seconds + 5,
            )
            return json.loads(result.stdout) if result.stdout.strip() else []

        # Collect from paired devices and live inquiry, deduplicated by address
        seen: dict[str, dict] = {}
        for device in run_blueutil("--paired"):
            seen[device["address"]] = device
        logger.info("Scanning for nearby devices (%ds)...", inquiry_seconds)
        for device in run_blueutil("--inquiry", str(inquiry_seconds)):
            seen.setdefault(device["address"], device)

        # Filter for Niimbot devices (name contains "B1", "D11", etc.)
        NIIMBOT_KEYWORDS = ("B1", "B21", "B3S", "D11", "D110", "D101")
        niimbot = [
            d for d in seen.values()
            if d.get("name") and any(kw in d["name"].upper() for kw in NIIMBOT_KEYWORDS)
        ]

        # Cross-reference with serial ports
        from serial.tools.list_ports import comports
        serial_ports = {p.split("/")[-1]: p for p, _, _ in comports()}

        devices = []
        for d in niimbot:
            port = next((p for pname, p in serial_ports.items() if d["name"] in pname), None)
            devices.append({
                "name": d.get("name", d["address"]),
                "mac": d["address"],
                "port": port,
                "connected": d.get("connected", False),
            })
        return devices

    @staticmethod
    def wait_for_serial_port(device_name: str, timeout: int = 10) -> str | None:
        """Poll until the serial port for the given device name appears, then return its path."""
        import glob
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            matches = glob.glob(f"/dev/cu.{device_name}*")
            if matches:
                return matches[0]
            time.sleep(0.5)
        return None

    @staticmethod
    def bluetooth_connect(mac: str) -> None:
        """Connect to a Bluetooth device by MAC address using blueutil."""
        import subprocess
        logger.info("Connecting to %s via Bluetooth...", mac)
        subprocess.run(["blueutil", "--connect", mac], check=True)
        # Give the OS a moment to fully establish the connection before the serial port is opened
        time.sleep(3)

    @staticmethod
    def bluetooth_forget(mac: str) -> None:
        """Unpair a Bluetooth device so the next connect triggers a fresh pairing.

        This is the only reliable way to reset the RFCOMM channel state on macOS —
        a simple disconnect leaves stale state that causes the printer to ignore
        packets on the next session.
        """
        import subprocess
        logger.info("Unpairing %s to reset Bluetooth state for next session...", mac)
        subprocess.run(["blueutil", "--unpair", mac], check=False)
