import argparse
import signal
import sys

import logger as log_module
from differ import Differ
from printer import Printer, PrinterConnectionError
from watcher import Watcher


def parse_args():
    parser = argparse.ArgumentParser(
        description="HotTicket — print new TODO lines on your Niimbot B1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py tasks.txt --connect\n"
            "  python main.py tasks.txt --device /dev/cu.B1-F529062396\n"
            "  python main.py --discover\n"
            "  python main.py tasks.txt --connect --dry-run --debug"
        ),
    )
    parser.add_argument("file", nargs="?", help="Path to the TODO file to watch")
    parser.add_argument("--device", help="Serial port path for the Niimbot")
    parser.add_argument("--connect", action="store_true", help="Auto-discover and connect to the first Niimbot found")
    parser.add_argument("--discover", action="store_true", help="Scan for nearby Niimbot devices and show connect commands")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging")
    parser.add_argument("--dry-run", action="store_true", help="Log labels instead of printing")
    parser.add_argument("--density", type=int, default=3, choices=range(1, 6), metavar="1-5",
                        help="Print density 1 (lightest) to 5 (darkest), default 3")
    return parser.parse_args()


def run_discover(printer: Printer) -> None:
    print("Scanning for paired Niimbot devices...")
    devices = printer.scan_niimbot_devices()
    if not devices:
        print("No Niimbot devices found. Make sure the printer is on and paired via Bluetooth.")
        return
    for d in devices:
        port_info = d["port"] or "serial port not found — printer may be off"
        print(f"\nFound: {d['name']}")
        print(f"  MAC:     {d['mac']}")
        print(f"  Port:    {port_info}")
        if d["port"]:
            print(f"  Connect: python main.py <file> --device {d['port']}")
    print("\nOr use --connect to scan and select interactively.")


def main() -> int:
    args = parse_args()

    log_module.init(debug=args.debug)
    logger = log_module.get_logger(__name__)

    printer = Printer(dry_run=args.dry_run, density=args.density)

    if args.discover:
        run_discover(printer)
        return 0

    # Resolve device port
    device = args.device
    selected_mac: str | None = None
    if args.connect:
        if args.device:
            print("Error: --connect and --device are mutually exclusive.", file=sys.stderr)
            return 1
        devices = printer.scan_niimbot_devices()
        if not devices:
            print("No Niimbot devices found nearby. Make sure the printer is on.", file=sys.stderr)
            return 1
        if len(devices) == 1:
            selected = devices[0]
            status = "connected" if selected["connected"] else "not connected"
            print(f"Found: {selected['name']} ({status})")
            choice = input("Connect to this device? [Y/n]: ").strip().lower()
            if choice == "n":
                return 0
        else:
            print("Found Niimbot devices:")
            for i, d in enumerate(devices, 1):
                status = "connected" if d["connected"] else "not connected"
                print(f"  [{i}] {d['name']}  —  {status}")
            while True:
                choice = input("Select device [1]: ").strip() or "1"
                if choice.isdigit() and 1 <= int(choice) <= len(devices):
                    selected = devices[int(choice) - 1]
                    break
                print(f"Please enter a number between 1 and {len(devices)}.")
        selected_mac = selected["mac"]
        print(f"Connecting {selected['name']} via Bluetooth...")
        printer.bluetooth_connect(selected_mac)
        device = selected.get("port") or printer.wait_for_serial_port(selected["name"])
        if not device:
            print(f"Error: serial port for {selected['name']} did not appear after connecting.", file=sys.stderr)
            return 1

    # Validate required args for watch mode
    missing = []
    if not args.file:
        missing.append("<file>")
    if not device:
        missing.append("--device <port> or --connect")
    if missing:
        print(f"Error: {' and '.join(missing)} required in watch mode.", file=sys.stderr)
        print("Run with --discover to find your device.", file=sys.stderr)
        return 1

    # Read initial file content
    try:
        with open(args.file) as f:
            initial_lines = f.read().splitlines()
    except FileNotFoundError:
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        return 1

    # Connect printer
    try:
        printer.connect(device)
    except PrinterConnectionError as e:
        logger.error("Printer connection failed: %s", e)
        return 1

    # Set up differ
    differ = Differ()
    differ.load(initial_lines)

    # Define change callback
    def on_change():
        try:
            with open(args.file) as f:
                new_lines = f.read().splitlines()
        except OSError as e:
            logger.error("Could not read file: %s", e)
            return
        added = differ.diff(new_lines)
        for line in added:
            printer.print_label(line)
        differ.update(new_lines)

    watcher = Watcher(args.file, on_change)

    # SIGINT handler for clean shutdown
    def handle_sigint(sig, frame):
        logger.debug("Interrupted, shutting down...")
        watcher.stop()
        printer.close()
        if selected_mac:
            printer.bluetooth_forget(selected_mac)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    print(f"Watching {args.file!r} — press Ctrl+C to stop")
    try:
        watcher.start()
    except RuntimeError as e:
        logger.error("Failed to start watcher: %s", e)
        printer.close()
        if selected_mac:
            printer.bluetooth_forget(selected_mac)
        return 1

    try:
        watcher.join()
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        printer.close()
        if selected_mac:
            printer.bluetooth_forget(selected_mac)
        return 1

    # Watcher stopped cleanly (file deleted or observer stopped)
    printer.close()
    if selected_mac:
        printer.bluetooth_forget(selected_mac)
    if watcher.was_deleted():
        logger.warning("Stopped: watched file was deleted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
