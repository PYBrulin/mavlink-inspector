import argparse
import curses
import logging
import time

from pymavlink import mavutil

from base.custom_logger import setup_logger
from base.interactive_tree import TreeView
from base.mavlink_bus import MAVBus


def main(args, **kwargs) -> None:
    # Setup logger
    setup_logger(debug=args.debug)
    conn_bus = None
    conn = None

    try:
        logging.info("Trying to connect to the vehicle...")
        conn = mavutil.mavlink_connection(args.master)
        # Make sure the connection is valid
        conn.wait_heartbeat()
        logging.info("Connected to the vehicle.")

        # Create a vehicle object
        conn_bus = MAVBus(conn, debug=args.debug, details=args.details)
        conn_bus.run_thread()

        # Wait a moment for initial data
        time.sleep(2)

        # Disable console logging before starting curses to prevent interference
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        # Launch the interactive tree view
        tree_view = TreeView(conn_bus.vehicles)
        curses.wrapper(tree_view.run)

    except KeyboardInterrupt:
        logging.info("Keyboard interrupt received. Exiting...")
    except Exception as e:
        logging.error(e)
    finally:
        logging.info("Closing connection...")
        if conn_bus:
            conn_bus.terminate()
        if conn:
            conn.close()


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description="Vehicle Connection Script")
    arg_parser.add_argument("--master", type=str, default="tcp:127.0.0.1:5760", help="Vehicle connection string")
    arg_parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    arg_parser.add_argument("--details", action="store_true", help="Enable detailed output")
    args = arg_parser.parse_args()

    main(args)
