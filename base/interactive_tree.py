"""
Console-based interactive treeview with keyboard controls
Uses curses for full keyboard interaction and real-time updates
"""

import curses
import threading
import time
from collections import defaultdict
from datetime import datetime

from pymavlink import mavutil


class TreeView:
    """Console tree view with keyboard navigation and expandable nodes"""

    def __init__(self, vehicles_dict=None):
        """
        Initialize the tree view

        Args:
            vehicles_dict: A dictionary or defaultdict of vehicles from MAVBus
        """
        self.vehicles_dict = vehicles_dict if vehicles_dict is not None else defaultdict(dict)
        self.data = {}
        self.selected_index = 0
        self.running = True
        self.flat_tree = []
        self._last_update = time.time()
        self.show_status_messages = True  # Toggle for status message panel
        self.status_messages = []  # List of (timestamp, vehicle_id, message) tuples
        self.max_status_messages = 100  # Keep last 100 messages

    def flatten_tree(self, data, level=0, parent_key="Root"):
        """Convert nested dict to flat list for display"""
        result = []
        for key, value in data.items():
            if key.startswith("_"):
                continue

            is_expanded = value.get("_expanded", False)
            has_children = "_children" in value
            # has_value = "_value" in value

            item = {
                "key": key,
                "level": level,
                "expanded": is_expanded,
                "has_children": has_children,
                "parent": parent_key,
                "data": value,
            }
            result.append(item)

            if has_children and is_expanded:
                children = self.flatten_tree(value["_children"], level + 1, key)
                result.extend(children)

        return result

    def build_data_from_vehicles(self):
        """Build tree data structure from MAVBus vehicles dictionary"""
        new_data = {}

        for vehicle_id, component in self.vehicles_dict.items():
            # Preserve expansion state if this vehicle already exists
            vehicle_expanded = self.data.get(vehicle_id, {}).get("_expanded", True)

            vehicle_node = {"_expanded": vehicle_expanded, "_children": {}}

            # Add system and component IDs
            if hasattr(component, "system_id") and component.system_id is not None:
                vehicle_node["_children"]["System ID"] = {"_value": component.system_id, "_unit": "", "_expanded": False}
            if hasattr(component, "component_id") and component.component_id is not None:
                try:
                    component_name = mavutil.mavlink.enums["MAV_COMPONENT"].get(component.component_id, "")
                    component_name = component_name.name if component_name else ""
                except Exception:
                    component_name = ""
                vehicle_node["_children"]["Component ID"] = {
                    "_value": f"{component.component_id} {component_name}",
                    "_unit": "",
                    "_expanded": False,
                }

            # Add message data section
            if hasattr(component, "data") and component.data:
                data_expanded = self.data.get(vehicle_id, {}).get("_children", {}).get("Messages", {}).get("_expanded", True)
                data_node = {"_expanded": data_expanded, "_children": {}}

                for msg_type, msg_data in component.data.items():
                    # Use stable key for expansion state lookup (without frequency info)
                    msg_expanded = (
                        self.data.get(vehicle_id, {})
                        .get("_children", {})
                        .get("Messages", {})
                        .get("_children", {})
                        .get(msg_type, {})
                        .get("_expanded", False)
                    )

                    # Get frequency information if available
                    frequency_info = ""
                    if hasattr(component, "message_stats") and msg_type in component.message_stats:
                        stats = component.message_stats[msg_type]
                        freq = stats["frequency"]
                        count = stats["count"]
                        if freq > 0:
                            frequency_info = f" [{freq:.1f} Hz, {count} msgs]"
                        else:
                            frequency_info = f" [{count} msgs]"

                    # Handle both dict and simple string/value types
                    if isinstance(msg_data, dict):
                        msg_node = {"_expanded": msg_expanded, "_children": {}}
                        # Add frequency as first child if available
                        if frequency_info:
                            msg_node["_children"]["_frequency"] = {
                                "_value": frequency_info.strip("[] "),
                                "_unit": "",
                                "_expanded": False,
                            }
                        # Add message fields as children
                        for field, value in msg_data.items():
                            # Format the value appropriately
                            if isinstance(value, float):
                                display_value = f"{value:.4f}"
                            else:
                                display_value = str(value)

                            msg_node["_children"][field] = {"_value": display_value, "_unit": "", "_expanded": False}

                        # Store with frequency info for display, but keep stable reference
                        msg_node["_display_suffix"] = frequency_info
                        data_node["_children"][msg_type] = msg_node
                    else:
                        # msg_data is a simple value (string, int, float, etc.)
                        # Display it as expandable node with lines as children
                        msg_node = {"_expanded": msg_expanded, "_children": {}}

                        # Convert to string and split by newlines
                        if isinstance(msg_data, float):
                            content_str = f"{msg_data:.4f}"
                        else:
                            content_str = str(msg_data)

                        # Split into lines and create a child for each line
                        lines = content_str.split("\n")
                        for idx, line in enumerate(lines):
                            if idx == len(lines) - 1 and line == "":
                                continue  # Skip adding empty last line
                            line_key = f"{idx + 1:03}" if len(lines) > 1 else "000"
                            msg_node["_children"][line_key] = {"_value": line, "_unit": "", "_expanded": False}

                        # Store with frequency info for display, but keep stable reference
                        msg_node["_display_suffix"] = frequency_info
                        data_node["_children"][msg_type] = msg_node

                if data_node["_children"]:
                    vehicle_node["_children"]["Messages"] = data_node

            # Add parameters section
            if hasattr(component, "parameters") and component.parameters:
                params_expanded = (
                    self.data.get(vehicle_id, {}).get("_children", {}).get("Parameters", {}).get("_expanded", False)
                )
                params_node = {"_expanded": params_expanded, "_children": {}}

                for param_id, param_value in component.parameters.items():
                    # Format parameter value
                    if isinstance(param_value, float):
                        display_value = f"{param_value:.4f}"
                    else:
                        display_value = str(param_value)

                    params_node["_children"][param_id] = {"_value": display_value, "_unit": "", "_expanded": False}

                if params_node["_children"]:
                    vehicle_node["_children"]["Parameters"] = params_node

            new_data[vehicle_id] = vehicle_node

        self.data = new_data

    def collect_status_messages(self):
        """Collect STATUSTEXT messages from vehicles"""
        for vehicle_id, component in self.vehicles_dict.items():
            if hasattr(component, "status_messages") and component.status_messages:
                # Process new messages we haven't seen yet
                for msg in component.status_messages:
                    timestamp_str = datetime.fromtimestamp(msg["timestamp"]).strftime("%H:%M:%S")
                    text = msg["text"]
                    msg_tuple = (timestamp_str, vehicle_id, text)

                    # Only add if it's not already in our list
                    if msg_tuple not in self.status_messages:
                        self.status_messages.append(msg_tuple)

                # Keep only last N messages
                if len(self.status_messages) > self.max_status_messages:
                    self.status_messages = self.status_messages[-self.max_status_messages :]

    def update_data(self):
        """Update data from vehicles dictionary in real-time"""
        while self.running:
            self.build_data_from_vehicles()
            self.collect_status_messages()
            self._last_update = time.time()
            time.sleep(0.5)  # Update twice per second

    def toggle_expand(self, index):
        """Toggle expand/collapse state of selected item"""
        if 0 <= index < len(self.flat_tree):
            item = self.flat_tree[index]
            if item["has_children"]:
                item["data"]["_expanded"] = not item["data"]["_expanded"]

    def draw_screen(self, stdscr):
        """Draw the tree on screen"""
        height, width = stdscr.getmaxyx()
        stdscr.erase()  # Use erase() instead of clear() to reduce flicker

        # Draw title
        title = "MAVLink Inspector"
        timestamp = datetime.now().strftime("%H:%M:%S")
        stdscr.addstr(0, 0, title[: width - 1], curses.A_BOLD | curses.color_pair(1))
        stdscr.addstr(
            1,
            0,
            f"Last update: {timestamp} | 'q' quit | ↑↓ navigate | ←→ collapse/expand | Space toggle | s status | e/c all",
            curses.color_pair(3),
        )
        stdscr.addstr(2, 0, "─" * (width - 1))

        # Flatten tree for display
        self.flat_tree = self.flatten_tree(self.data)

        # Calculate available space for tree and status panel
        status_panel_height = 8 if self.show_status_messages else 0
        tree_bottom = height - status_panel_height - 1  # -1 for footer

        # Show message if no vehicles
        if not self.flat_tree:
            msg = "Waiting for vehicles... (No data yet)"
            try:
                stdscr.addstr(4, 2, msg, curses.color_pair(3))
            except curses.error:
                pass
            stdscr.noutrefresh()
            return

        # Draw tree items
        tree_display_height = tree_bottom - 3  # 3 for header
        display_start = max(0, self.selected_index - (tree_display_height - 5))
        display_end = min(len(self.flat_tree), display_start + tree_display_height)

        for i in range(display_start, display_end):
            item = self.flat_tree[i]
            y = 3 + (i - display_start)

            if y >= tree_bottom:
                break

            # Indent based on level
            indent = "  " * item["level"]

            # Expansion indicator
            if item["has_children"]:
                indicator = "▼ " if item["expanded"] else "▶ "
            else:
                indicator = "  "

            # Build display string
            display_str = f"{indent}{indicator}{item['key']}"

            # Add display suffix if present (for frequency info)
            if "_display_suffix" in item["data"]:
                display_str += item["data"]["_display_suffix"]

            # Add value if present
            if "_value" in item["data"]:
                value = item["data"]["_value"]
                unit = item["data"].get("_unit", "")
                display_str += f": {value}{unit}"

            # Highlight selected item
            attr = curses.A_REVERSE if i == self.selected_index else curses.A_NORMAL

            # Color coding
            if item["has_children"]:
                color = curses.color_pair(2)  # Cyan for branches
            else:
                color = curses.color_pair(4)  # Green for leaves

            try:
                stdscr.addstr(y, 0, display_str[: width - 1], attr | color)
            except curses.error:
                pass

        # Draw status message panel if enabled
        if self.show_status_messages:
            panel_start = tree_bottom
            try:
                # Draw separator
                stdscr.addstr(panel_start, 0, "─" * (width - 1), curses.color_pair(3))
                stdscr.addstr(panel_start + 1, 0, "STATUS MESSAGES (press 's' to toggle)", curses.A_BOLD | curses.color_pair(1))

                # Draw last N status messages
                messages_to_show = min(5, len(self.status_messages))
                for i in range(messages_to_show):
                    msg_idx = len(self.status_messages) - messages_to_show + i
                    timestamp, vehicle_id, text = self.status_messages[msg_idx]
                    msg_line = f"[{timestamp}] [{vehicle_id}] {text}"
                    y = panel_start + 2 + i
                    if y < height - 1:
                        stdscr.addstr(y, 0, msg_line[: width - 1], curses.color_pair(3))
            except curses.error:
                pass

        # Draw footer
        try:
            footer = f"Selected: {self.selected_index + 1}/{len(self.flat_tree)} | Vehicles: {len(self.vehicles_dict)} | Status msgs: {len(self.status_messages)}"
            stdscr.addstr(height - 1, 0, footer[: width - 1], curses.color_pair(3))
        except curses.error:
            pass

        stdscr.noutrefresh()  # Mark for refresh without updating screen yet

    def run(self, stdscr):
        """Main event loop"""
        # Initialize colors
        curses.start_color()
        curses.init_pair(1, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_GREEN, curses.COLOR_BLACK)

        # Configure curses
        curses.curs_set(0)  # Hide cursor
        stdscr.timeout(500)  # Non-blocking input with 500ms timeout
        stdscr.idlok(True)  # Enable hardware line insertion/deletion
        stdscr.scrollok(False)  # Disable scrolling

        # Start data update thread
        update_thread = threading.Thread(target=self.update_data, daemon=True)
        update_thread.start()

        # Main loop
        while self.running:
            self.draw_screen(stdscr)
            curses.doupdate()  # Update physical screen once for all windows

            # Handle input
            try:
                key = stdscr.getch()

                if key == ord("q") or key == ord("Q"):
                    self.running = False
                elif key == curses.KEY_UP:
                    self.selected_index = max(0, self.selected_index - 1)
                elif key == curses.KEY_DOWN:
                    self.selected_index = min(len(self.flat_tree) - 1, self.selected_index + 1)
                elif key == curses.KEY_RIGHT:
                    # Expand the selected node
                    if 0 <= self.selected_index < len(self.flat_tree):
                        item = self.flat_tree[self.selected_index]
                        if item["has_children"] and not item["expanded"]:
                            item["data"]["_expanded"] = True
                elif key == curses.KEY_LEFT:
                    # Collapse the selected node, or move to parent if already collapsed
                    if 0 <= self.selected_index < len(self.flat_tree):
                        item = self.flat_tree[self.selected_index]
                        if item["has_children"] and item["expanded"]:
                            # Node is expanded, collapse it
                            item["data"]["_expanded"] = False
                        else:
                            # Node is collapsed or has no children, navigate to parent
                            current_level = item["level"]
                            parent_key = item["parent"]
                            # Search upwards for the parent
                            for i in range(self.selected_index - 1, -1, -1):
                                parent_item = self.flat_tree[i]
                                if parent_item["level"] < current_level and parent_item["key"] == parent_key:
                                    self.selected_index = i
                                    break
                elif key == ord(" ") or key == ord("\n") or key == curses.KEY_ENTER:
                    self.toggle_expand(self.selected_index)
                elif key == ord("s") or key == ord("S"):  # Toggle status panel
                    self.show_status_messages = not self.show_status_messages
                elif key == ord("e"):  # Expand all
                    for item in self.flat_tree:
                        if item["has_children"]:
                            item["data"]["_expanded"] = True
                elif key == ord("c"):  # Collapse all
                    for item in self.flat_tree:
                        if item["has_children"]:
                            item["data"]["_expanded"] = False
            except curses.error:
                pass
