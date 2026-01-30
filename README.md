# MAVLink Inspector

An interactive console-based tree view for inspecting MAVLink vehicle data in real-time.

## Usage

### Main Application

Connect to a MAVLink vehicle and display its data:

```bash
python main.py --master tcp:127.0.0.1:5760
```

Options:

- `--master`: Connection string (default: `tcp:127.0.0.1:5760`)
- `--details`: Show detailed message fields in the tree view
- `--debug`: Enable debug logging

### Standalone Demo

Test the tree view with simulated data:

```bash
python interactive_tree_advanced.py
```

## Keyboard Controls

| Key               | Action                                                   |
| ----------------- | -------------------------------------------------------- |
| `↑` / `↓`         | Navigate up/down through items                           |
| `→`               | Expand selected item (if collapsed)                      |
| `←`               | Collapse selected item, or jump to parent (if collapsed) |
| `Space` / `Enter` | Toggle expand/collapse                                   |
| `s`               | Toggle status message panel                              |
| `e`               | Expand all nodes                                         |
| `c`               | Collapse all nodes                                       |
| `q`               | Quit the application                                     |

## Data Structure

The tree view displays data in the following hierarchy:

```
Vehicle ID (e.g., "1:1")
├── System ID: 1
├── Component ID: 1
├── Messages
│   ├── HEARTBEAT [50.0 Hz, 1234 msgs] (expandable - dict with fields)
│   │   ├── type: 0
│   │   ├── autopilot: 3
│   │   ├── base_mode: 81
│   │   └── custom_mode: 0
│   ├── ATTITUDE [100.0 Hz, 2468 msgs]
│   │   ├── roll: 0.0234
│   │   ├── pitch: -0.0156
│   │   └── yaw: 1.5708
│   ├── SYS_STATUS [1.0 Hz, 25 msgs] (expandable - multi-line string)
│   │   ├── 001: MY MULTI-LINE STRING HERE
│   │   ├── 002: CONTINUING ON LINE 2
│   │   └── 003: AND LINE 3, ETC.
│   └── ... (other message types)
└── Parameters
    ├── PARAM1: 1.5
    ├── PARAM2: 2.0
    └── ... (other parameters)
```

**Message Frequency Tracking**: Each message type displays its reception frequency (Hz) and total message count next to its name.
