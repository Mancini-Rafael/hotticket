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
            "  python main.py tasks.txt --device AA:BB:CC:DD:EE:FF\n"
            "  python main.py --discover\n"
            "  python main.py tasks.txt --device AA:BB:CC:DD:EE:FF --dry-run --debug"
        ),
    )
    parser.add_argument("file", nargs="?", help="Path to the TODO file to watch")
    parser.add_argument("--device", help="Bluetooth MAC address of the Niimbot B1")
    parser.add_argument("--discover", action="store_true", help="Scan for nearby Niimbot devices")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging")
    parser.add_argument("--dry-run", action="store_true", help="Log labels instead of printing")
    return parser.parse_args()


def run_discover(printer: Printer) -> None:
    print("Scanning for nearby Niimbot devices (5s)...")
    devices = printer.discover()
    if not devices:
        print("No Niimbot devices found.")
    else:
        for d in devices:
            print(f"  {d['name']}  —  {d['address']}")


def main() -> int:
    args = parse_args()

    log_module.init(debug=args.debug)
    logger = log_module.get_logger(__name__)

    printer = Printer(dry_run=args.dry_run)

    if args.discover:
        run_discover(printer)
        return 0

    # Validate required args for watch mode
    missing = []
    if not args.file:
        missing.append("<file>")
    if not args.device:
        missing.append("--device <MAC>")
    if missing:
        print(f"Error: {' and '.join(missing)} required in watch mode.", file=sys.stderr)
        print("Run with --discover to find your device's MAC address.", file=sys.stderr)
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
        printer.connect(args.device)
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

    # Set up watcher
    watcher = Watcher(args.file, on_change, lambda: None)

    # SIGINT handler for clean shutdown
    def handle_sigint(sig, frame):
        logger.debug("Interrupted, shutting down...")
        watcher.stop()
        printer.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    print(f"Watching {args.file!r} — press Ctrl+C to stop")
    watcher.start()

    try:
        watcher.join()
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        printer.close()
        return 1

    # Watcher stopped cleanly (file deleted or observer stopped)
    printer.close()
    if watcher.was_deleted():
        logger.warning("Stopped: watched file was deleted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
