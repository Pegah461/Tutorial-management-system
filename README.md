# Tutorial Management System

A desktop tutorial-session manager built for CS310 (computer networks). A **tutor server** takes attendance, hosts a group chat and runs a timed 30-minute discussion. During the discussion, **student clients** can also message each other directly over peer-to-peer connections.

Both apps are written in Python with Tkinter and use only the standard library. They show three networking techniques side by side:

| Feature | Transport | Port |
| --- | --- | --- |
| Attendance check-in and session control | Raw IP socket with hand-built IP/TCP headers | 5000 (server), 1234 (client) |
| Group chat | TCP | 5001 |
| P2P coordination (peer registration and lookup) | TCP | 5002 |
| Direct student-to-student chat | TCP | Random port per client, 5050–6050 |

## Project structure

```
CS310 Tutorial Management System/
├── TMSserver.py   # Tutor server GUI: attendance, chat, P2P coordination, discussion timer
└── TMSClient.py   # Student client GUI: check-in, group chat, P2P chat
```

## Requirements

- **Windows.** Raw sockets use `SIO_RCVALL`, which only exists on Windows.
- **Administrator privileges** for both the server and the clients, because raw sockets need them. Without them, the app shows "Please run as administrator" and exits.
- **Python 3** with Tkinter (the standard python.org installer includes it). No third-party packages are needed.

## Running

Open a terminal **as Administrator** and start the server first:

```powershell
cd "CS310 Tutorial Management System"
python TMSserver.py
```

Then open one Administrator terminal per student and start a client in each:

```powershell
cd "CS310 Tutorial Management System"
python TMSClient.py
```

Each client asks for a **Student ID** and a **full name** at startup. If you cancel either prompt, the client closes.

> Both apps are hardcoded to `127.0.0.1`, so the server and every client must run on the same machine. To run across machines, change `self.server_ip` in both files.

## Using the system

### Tutor (server)

The server window has three tabs:

- **Attendance**: lists students who have checked in, with their name, ID and IP address.
  - **Refresh** redraws the list.
  - **Export List** writes `attendance_YYYYMMDD_HHMMSS.txt` (tab-separated name, ID, IP) to the current working directory.
  - **Start Discussion** starts the 30-minute discussion and notifies every checked-in student.
- **Chat**: shows online students, the group chat log and server events (joins, leaves, errors). Messages the tutor sends appear as `[Tutor]: ...`.
- **P2P Coordination**: lists students registered for P2P and their listening ports, plus the discussion countdown.

### Student (client)

- **Check-in**: click **Check In** to send attendance to the server. The status changes to *Check-in sent* and then to *Checked in at <time>* when the server acknowledges it.
- **Group Chat**: the client joins automatically at startup. Messages go to the tutor and to every other student. Typing `/exit` closes the client.
- **P2P Chat**: enabled once the tutor starts the discussion. Select a peer from the list and send direct messages to them. The peer list refreshes every 5 seconds while the discussion is active, or on demand with **Refresh Peers**.
- The status bar at the bottom shows the discussion countdown.

## How it works

### Check-in (raw sockets)

1. The client builds an IP header and a TCP header by hand with `struct.pack` and sends `CHECKIN:<id>:<name>` as the payload through a raw socket.
2. The server's raw socket is in promiscuous mode (`SIO_RCVALL`). It scans incoming packets for `CHECKIN:`, records the student, and replies with a raw `ACK:<id>:<timestamp>` packet.
3. When the tutor starts the discussion, the server sends a raw `START_DISCUSSION` packet to each checked-in student. Students who check in after the discussion has started receive it straight after their ACK.

### Group chat (TCP, port 5001)

| Message | Direction | Meaning |
| --- | --- | --- |
| `REGISTER:<id>:<name>` | client → server | Join the chat (sent automatically on connect) |
| `CHAT:<id>:<message>` | client → server | Post a message. The server relays it to everyone except the sender as `[<name>]: <message>` |

### P2P coordination (TCP, port 5002)

Each request uses a short-lived connection:

| Message | Response | Meaning |
| --- | --- | --- |
| `REGISTER_P2P:<id>:<port>` | `P2P_REGISTERED` | Advertise this client's P2P listening port. Only works if the student is connected to the group chat |
| `GET_PEERS:<id>` | `PEER_LIST:<id>\|<name>\|<port>,...` | List the other registered peers |

### Direct messages

Each client listens on a random port between 5050 and 6050. To message a peer, the client opens a TCP connection to that peer's port (and reuses it afterwards) and sends `P2P_MSG:<sender_id>:<message>`.

### Discussion timer

The discussion lasts 30 minutes (1800 s). The server and each client run their own countdowns. When it reaches zero, P2P is disabled on the clients.

## Known limitations

- **Windows-only, Administrator-only, localhost-only.** See [Requirements](#requirements).
- **The 5-minute warning never appears on clients.** The server sends `[WARNING]: Discussion ending in 5 minutes!`, but the client looks for `WARNING:`, which that string does not contain.
- **Countdowns can drift apart.** Each client starts its 30-minute countdown when it receives `START_DISCUSSION`, so a student who checks in late sees more time left than the tutor does.
- **The IP and TCP checksums are left at zero** in the hand-built packets. This works on loopback but may be dropped on a real network.
- **Messages have no framing.** Each `recv(1024)` is treated as one complete message, so long messages or messages sent in quick succession can be split or merged.
- **P2P messages show the sender's student ID**, not their name.
- **Background threads update Tkinter widgets directly.** Tkinter is not thread-safe, so the GUI can occasionally misbehave under load.
