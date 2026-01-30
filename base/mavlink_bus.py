import io as StringIO
import logging
import time
from collections import defaultdict
from threading import Thread

import pymavlink
from pymavlink import mavutil


class Component:
    """An object to store the component's information and methods"""

    def __init__(self) -> None:
        """Initialize the component object"""
        self.system_id = None
        self.component_id = None
        self.data = {}
        self.parameters = {}
        self.status_messages = []  # List to store all status messages
        self.message_stats = {}  # Dict to track message reception stats
        # message_stats structure: {msg_type: {'count': int, 'last_time': float, 'frequency': float}}


class MAVBus:
    """An object to store the vehicle's information and methods"""

    def __init__(
        self,
        connection: pymavlink.mavutil.mavlink_connection,
        debug: bool = False,
        details: bool = False,
    ) -> None:
        """Initialize the vehicle object"""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO if not debug else logging.DEBUG)

        self.connection = connection
        self.details = details
        self.mavlink_thread_in = None
        self._alive = False
        self.vehicles = defaultdict(Component)
        self.stats_update_interval = 0.5  # Update stats every 0.5 seconds

    def dump_message_verbose(self, m):
        """return verbose dump of m.  Wraps the pymavlink routine which
        inconveniently takes a filehandle"""
        f = StringIO.StringIO()
        mavutil.dump_message_verbose(f, m)
        return f.getvalue()

    def _update_message_stats(self, vehicle_id: str, msg_type: str) -> None:
        """Update message reception statistics for frequency tracking"""
        current_time = time.time()
        stats = self.vehicles[vehicle_id].message_stats

        if msg_type not in stats:
            # First message of this type
            stats[msg_type] = {
                "count": 1,
                "last_time": current_time,
                "first_time": current_time,
                "frequency": 0.0,  # Cannot calculate frequency with only one message
                "recent_timestamps": [current_time],  # Track recent message timestamps
            }
        else:
            # Update existing stats
            stats[msg_type]["count"] += 1
            stats[msg_type]["last_time"] = current_time

            # Add current timestamp to recent list
            stats[msg_type]["recent_timestamps"].append(current_time)

            # Recalculate frequency
            self._recalculate_frequency(stats[msg_type], current_time)

    def _recalculate_frequency(self, stat_entry: dict, current_time: float) -> None:
        """Recalculate frequency for a single message type"""
        # Remove timestamps older than 2 seconds
        window_start = current_time - 2.0
        stat_entry["recent_timestamps"] = [ts for ts in stat_entry["recent_timestamps"] if ts > window_start]

        # Calculate frequency (Hz) based on messages in the last 2 seconds
        recent_count = len(stat_entry["recent_timestamps"])
        if recent_count > 1:
            # Calculate time span of recent messages
            time_span = current_time - stat_entry["recent_timestamps"][0]
            if time_span > 0:
                stat_entry["frequency"] = (recent_count - 1) / time_span
            else:
                stat_entry["frequency"] = 0.0
        else:
            stat_entry["frequency"] = 0.0

    def _cleanup_and_update_stats(self) -> None:
        """Periodically clean up old timestamps and update frequencies"""
        current_time = time.time()
        for vehicle_id, component in self.vehicles.items():
            for msg_type, stat_entry in component.message_stats.items():
                self._recalculate_frequency(stat_entry, current_time)

    def parse_msg(self, msg: pymavlink.mavutil.mavlink.MAVLink) -> None:
        """Parse a message from the vehicle"""
        # msg = self.vehicle_conn.recv_match(blocking=False, timeout=1)
        if not msg:
            return

        if msg.get_type() == "BAD_DATA":
            # Ignore bad data
            return

        system = msg.get_srcSystem()
        component = msg.get_srcComponent()
        vehicle_id = f"{system}:{component}"
        if vehicle_id not in self.vehicles:
            self.vehicles[vehicle_id].system_id = system
            self.vehicles[vehicle_id].component_id = component

        # Update message statistics for this message type
        msg_type = msg.get_type()
        self._update_message_stats(vehicle_id, msg_type)

        if msg.get_type() == "STATUSTEXT":
            # Get severity
            severity = msg.to_dict().get("severity")

            # Store each status message in the list
            self.vehicles[vehicle_id].status_messages.append(
                {"timestamp": time.time(), "text": msg.to_dict().get("text"), "severity": severity}
            )

        elif msg.get_type() == "PARAM_VALUE":
            # Store parameter value
            param_id = msg.to_dict().get("param_id")
            param_value = msg.to_dict().get("param_value")
            self.vehicles[vehicle_id].parameters[param_id] = param_value

        else:
            self.logger.debug(f"Received {msg.get_type()} message")

            # Store the message data
            if self.details:
                self.vehicles[vehicle_id].data[msg.get_type()] = self.dump_message_verbose(msg)
            else:
                self.vehicles[vehicle_id].data[msg.get_type()] = msg.to_dict()

    @property
    def armed(self):
        """Return the vehicle's armed state"""
        return (self.heartbeat.get("base_mode", 0) & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED) != 0

    # endregion Properties

    # region Thread
    def thread_in(self) -> None:
        """Run the thread to parse messages from the vehicle"""
        try:
            while self._alive:
                msg = self.connection.recv_match(blocking=False, timeout=1)
                self.parse_msg(msg)
        except Exception as e:
            self.logger.exception(e)

    def thread_stats_update(self) -> None:
        """Run the thread to periodically update message statistics"""
        try:
            while self._alive:
                time.sleep(self.stats_update_interval)
                self._cleanup_and_update_stats()
        except Exception as e:
            self.logger.exception(e)

    def run_thread(self) -> None:
        """DroneKit-like thread to parse messages from the vehicle. RIP DroneKit"""
        self.connection.select(0.05)
        self._alive = True

        # Start message parsing thread
        t = Thread(target=self.thread_in)
        t.daemon = True
        self.mavlink_thread_in = t
        self.mavlink_thread_in.start()

        # Start stats update thread
        t_stats = Thread(target=self.thread_stats_update)
        t_stats.daemon = True
        t_stats.start()

    def terminate(self) -> None:
        """Terminate the vehicle connection"""
        self.logger.info("Terminating vehicle connection")
        self._alive = False
        if self.mavlink_thread_in is not None:
            self.mavlink_thread_in.join()
            self.mavlink_thread_in = None

    # endregion
