import socket
import struct
import threading
import time
from tkinter import *
from tkinter import scrolledtext, messagebox, ttk

class ServerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TUTOR SERVER")
        self.root.geometry("800x600")
        self.peers_lock = threading.Lock()
        self.p2p_peers_lock = threading.Lock()
        self.discussion_active = False
        
        # NETWORK SETUP
        self.server_ip = '127.0.0.1'
        self.checkin_port = 5000 # USE PORT 5000 TO LISTEN FOR STUDENT CHECK-IN (ATTENDANCE)
        self.chat_port = 5001   # USE PORT 5001 TO LISTEN FOR INCOMING MESSAGES
        self.p2p_port = 5002    # USE PORT 5002 FOR PEER-TO-PEER COORDINATION
        self.running = True
        self.attendance = {}
        self.peers = {}
        self.p2p_peers = {}
        self.discussion_start_time = None
        
        # CREATE GUI USING TKINTER LIBRARY
        self.create_widgets()
        
        # START SERVER
        self.start_server()

    def create_widgets(self):
        # NOTEBOOK FOR TABS
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=BOTH, expand=True)
        
        # ATTENDANCE TAB
        self.attendance_tab = Frame(self.notebook)
        self.notebook.add(self.attendance_tab, text="Attendance")
        self.setup_attendance_tab()
        
        # CHAT TAB
        self.chat_tab = Frame(self.notebook)
        self.notebook.add(self.chat_tab, text="Chat")
        self.setup_chat_tab()
        
        # P2P TAB
        self.p2p_tab = Frame(self.notebook)
        self.notebook.add(self.p2p_tab, text="P2P Coordination")
        self.setup_p2p_tab()
        
        # STATUS BAR
        self.status_bar = Label(self.root, text=f"[Server Running On] {self.server_ip}", bd=1, relief=SUNKEN, anchor=W)
        self.status_bar.pack(side=BOTTOM, fill=X)

    def setup_attendance_tab(self):
        # LIST OF STUDENTS WHO HAVE CHECKED IN
        Label(self.attendance_tab, text="Student Attendance", font=('Arial', 12, 'bold')).pack(pady=5)
        
        self.attendance_list = Listbox(self.attendance_tab, height=15)
        self.attendance_list.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        # BUTTON FRAME
        btn_frame = Frame(self.attendance_tab)
        btn_frame.pack(fill=X, padx=10, pady=5)
        
        Button(btn_frame, text="Refresh", command=self.update_attendance_list).pack(side=LEFT, padx=5)
        Button(btn_frame, text="Start Discussion", command=self.start_discussion).pack(side=RIGHT, padx=5)
        Button(btn_frame, text="Export List", command=self.export_attendance).pack(side=RIGHT, padx=5)

    def setup_chat_tab(self):
        # Online Students Frame
        online_frame = Frame(self.chat_tab)
        online_frame.pack(fill=X, padx=10, pady=5)
        
        Label(online_frame, text="Online Students", font=('Arial', 10)).pack(side=LEFT)
        self.online_count = Label(online_frame, text="0")
        self.online_count.pack(side=LEFT, padx=5)
        
        self.online_listbox = Listbox(self.chat_tab, height=8)
        self.online_listbox.pack(fill=BOTH, expand=False, padx=10, pady=5)
        
        # DISPLAY MESSAGES
        self.chat_display = scrolledtext.ScrolledText(self.chat_tab, state='disabled')
        self.chat_display.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        # MESSAGE INPUT
        msg_frame = Frame(self.chat_tab)
        msg_frame.pack(fill=X, padx=10, pady=5)
        
        self.message_entry = Entry(msg_frame)
        self.message_entry.pack(side=LEFT, fill=X, expand=True, padx=5)
        self.message_entry.bind("<Return>", lambda e: self.send_chat_message())
        
        Button(msg_frame, text="Send", command=self.send_chat_message).pack(side=RIGHT)

    def setup_p2p_tab(self):
        Label(self.p2p_tab, text="P2P Connections", font=('Arial', 12, 'bold')).pack(pady=5)
        self.p2p_listbox = Listbox(self.p2p_tab, height=15)
        self.p2p_listbox.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        self.time_label = Label(self.p2p_tab, text="Discussion not started", fg="red")
        self.time_label.pack(pady=5)
        
        btn_frame = Frame(self.p2p_tab)
        btn_frame.pack(fill=X, padx=10, pady=5)
        Button(btn_frame, text="Refresh", command=self.update_p2p_list).pack(side=LEFT, padx=5)

    def start_server(self):
        # START RAW SOCKET FOR STUDENT CHECK-IN
        try:
            self.raw_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_IP)
            self.raw_socket.bind((self.server_ip, self.checkin_port))
            self.raw_socket.ioctl(socket.SIO_RCVALL, socket.RCVALL_ON)
            
            threading.Thread(target=self.handle_checkins, daemon=True).start()
        except PermissionError:
            messagebox.showerror("Error", "Please run as administrator")
            self.root.destroy()
            return
            
        # START TCP SOCKET FOR CHAT
        self.chat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.chat_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.chat_socket.bind((self.server_ip, self.chat_port))
        self.chat_socket.listen(5)
        
        threading.Thread(target=self.accept_chat_connections, daemon=True).start()
        
        # START TCP SOCKET FOR P2P COORDINATION
        self.p2p_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.p2p_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.p2p_socket.bind((self.server_ip, self.p2p_port))
        self.p2p_socket.listen(5)
        
        threading.Thread(target=self.accept_p2p_connections, daemon=True).start()

    # THIS PART HANDLES THE CHECKIN FROM STUDENTS. 
    def handle_checkins(self):
        while self.running:
            try:
                packet, addr = self.raw_socket.recvfrom(65535)
                if b"CHECKIN:" in packet:
                    payload = packet.split(b"CHECKIN:")[1].decode().split('\x00')[0]
                    student_id, name = payload.split(":")
                    self.attendance[student_id] = (name, addr[0])
                    
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                    ack_packet = self.build_raw_packet(
                        self.server_ip, addr[0],
                        self.checkin_port, 1234,
                        f"ACK:{student_id}:{timestamp}"
                    )
                    self.raw_socket.sendto(ack_packet, (addr[0], 0))
                    
                    # If discussion is active, notify the new student immediately
                    if self.discussion_active:
                        start_packet = self.build_raw_packet(
                            self.server_ip, addr[0],
                            self.checkin_port, 1234,
                            "START_DISCUSSION"
                        )
                        self.raw_socket.sendto(start_packet, (addr[0], 0))
                    
                    self.update_attendance_list()
                    
            except Exception as e:
                if self.running:
                    self.log_message(f"Check-in error: {e}")

    # ACCEPT CHAT CONNECTIONS (CHAT TCP SOCKET)
    def accept_chat_connections(self):
        while self.running:
            try:
                conn, addr = self.chat_socket.accept()
                threading.Thread(target=self.handle_chat_client, args=(conn,), daemon=True).start()
            except:
                if self.running:
                    self.log_message("Chat Socket Closed")

    # ACCEPT P2P CONNECTIONS 
    def accept_p2p_connections(self):
        while self.running:
            try:
                conn, addr = self.p2p_socket.accept()
                threading.Thread(target=self.handle_p2p_client, args=(conn,), daemon=True).start()
            except:
                if self.running:
                    self.log_message("P2P Socket Closed")

    # HANDLE MESSAGES IN THE GROUP CHAT
    def handle_chat_client(self, conn):
        student_id = None
        try:
            while self.running:
                data = conn.recv(1024).decode()
                if not data:
                    break
                    
                if data.startswith("REGISTER:"):
                    _, student_id, name = data.split(":", 2)
                    with self.peers_lock:
                        self.peers[student_id] = (name, conn)
                    self.update_online_list()
                    self.log_message(f"{name} joined the chat")
                    
                elif data.startswith("CHAT:"):
                    _, sender_id, message = data.split(":", 2)
                    with self.peers_lock:
                        sender_name = self.peers.get(sender_id, ("Unknown", None))[0]
                    formatted_message = f"[{sender_name}]: {message}"
                    self.log_message(formatted_message)
                    
                    # Broadcast to all connected clients
                    with self.peers_lock:
                        peers_copy = list(self.peers.items())
                    for peer_id, (_, peer_conn) in peers_copy:
                        if peer_id != sender_id:  # Don't send back to sender
                            try:
                                peer_conn.send(formatted_message.encode())
                            except:
                                with self.peers_lock:
                                    if peer_id in self.peers:
                                        del self.peers[peer_id]
                                self.update_online_list()
                    
        except Exception as e:
            pass
        finally:
            if student_id:
                with self.peers_lock:
                    if student_id in self.peers:
                        name = self.peers[student_id][0]
                        self.log_message(f"{name} left the chat")
                        del self.peers[student_id]
                with self.p2p_peers_lock:
                    if student_id in self.p2p_peers:
                        del self.p2p_peers[student_id]
                self.update_online_list()
                self.update_p2p_list()
            conn.close()

    # HANDLE REGISTRATION OF STUDENTS (P2P CONN)
    def handle_p2p_client(self, conn):
        try:
            data = conn.recv(1024).decode()
            if not data:
                return
                
            if data.startswith("REGISTER_P2P:"):
                _, student_id, p2p_port = data.split(":")
                with self.peers_lock:
                    if student_id in self.peers:
                        name = self.peers[student_id][0]
                        with self.p2p_peers_lock:
                            self.p2p_peers[student_id] = (name, int(p2p_port))
                        self.update_p2p_list()
                        conn.send("P2P_REGISTERED".encode())
                        
            elif data.startswith("GET_PEERS:"):
                student_id = data.split(":")[1]
                peer_list = []
                with self.p2p_peers_lock:
                    p2p_peers_copy = list(self.p2p_peers.items())
                for peer_id, (peer_name, peer_port) in p2p_peers_copy:
                    if peer_id != student_id:
                        peer_list.append(f"{peer_id}|{peer_name}|{peer_port}")
                response = "PEER_LIST:" + ",".join(peer_list)
                conn.send(response.encode())
            
        except Exception as e:
            self.log_message(f"P2P error: {e}")
        finally:
            conn.close()

    def start_discussion(self):
        self.discussion_start_time = time.time()
        self.discussion_active = True  # Set discussion as active
        self.time_label.config(text="30 min Discussion Session Has Started", fg="green")
        
        # Send START_DISCUSSION to all students (including those who check in later)
        for student_id, (_, ip) in self.attendance.items():
            try:
                packet = self.build_raw_packet(
                    self.server_ip, ip,
                    self.checkin_port, 1234,
                    "START_DISCUSSION"
                )
                self.raw_socket.sendto(packet, (ip, 0))
            except Exception as e:
                self.log_message(f"Failed To Notify {student_id}: {e}")
        
        threading.Thread(target=self.discussion_timer, daemon=True).start()

    def discussion_timer(self):
        while self.running and self.discussion_start_time:
            elapsed = time.time() - self.discussion_start_time
            remaining = max(0, 1800 - elapsed)
            mins, secs = divmod(remaining, 60)
            self.time_label.config(text=f"Time Remaining: {int(mins)}:{int(secs):02d}")
            
            if 300 < remaining <= 305:
                for student_id, (_, ip) in self.attendance.items():
                    try:
                        packet = self.build_raw_packet(
                            self.server_ip, ip,
                            self.checkin_port, 1234,
                            "[WARNING]: Discussion ending in 5 minutes!"
                        )
                        self.raw_socket.sendto(packet, (ip, 0))
                    except:
                        pass
            
            if remaining <= 0:
                self.discussion_active = False  # Discussion is no longer active
                self.time_label.config(text="Discussion has ended", fg="red")
                break
            time.sleep(1)
    
    # MANUALLY BUILD RAW PACKET AND HEADERS FOR THE RAW SOCKET
    def build_raw_packet(self, src_addr, dst_addr, src_port, dst_port, payload):
        # Manually contruct a TCP packet with headers
        ip_header = struct.pack('!BBHHHBBH4s4s',
            0x45, 0, 20 + 20 + len(payload),  # Version/IHL, TOS, Total Length
            54321, 0, 64, socket.IPPROTO_TCP, 0,  # ID, Flags, TTL, Protocol, Checksum
            socket.inet_aton(src_addr), socket.inet_aton(dst_addr)
        )
        
        tcp_header = struct.pack('!HHLLBBHHH',
            src_port, dst_port,
            12345, 0,
            (5 << 4), 0b00000010,  # Data offset, Flags (SYN)
            5840, 0, 0  # Window, Checksum, Pointer
        )
        
        return ip_header + tcp_header + payload.encode()

    # UPDATE THE LIST OF STUDENTS WHO HAVE CHECKED IN AND THEIR IP
    def update_attendance_list(self):
        self.attendance_list.delete(0, END)
        for student_id, (name, ip) in self.attendance.items():
            self.attendance_list.insert(END, f"{name} ({student_id}) - {ip}")

    def update_online_list(self):
        self.online_listbox.delete(0, END)
        for student_id, (name, _) in self.peers.items():
            self.online_listbox.insert(END, f"{name} ({student_id})")
        self.online_count.config(text=str(len(self.peers)))

    def update_p2p_list(self):
        self.p2p_listbox.delete(0, END)
        for student_id, (name, port) in self.p2p_peers.items():
            self.p2p_listbox.insert(END, f"{name} ({student_id}) - Port: {port}")

    def log_message(self, message):
        self.chat_display.config(state='normal')
        self.chat_display.insert(END, message + "\n")
        self.chat_display.config(state='disabled')
        self.chat_display.see(END)

    def send_chat_message(self):
        message = self.message_entry.get().strip()
        if not message:
            return
            
        formatted_message = f"[Tutor]: {message}"
        self.log_message(formatted_message)
        self.message_entry.delete(0, END)
        
        for student_id, (_, conn) in list(self.peers.items()):
            try:
                conn.send(formatted_message.encode())
            except:
                if student_id in self.peers:
                    del self.peers[student_id]
                    self.update_online_list()

    # EXPORT ATTENDANCE LIST TO A TEXT FILE
    def export_attendance(self):
        filename = f"attendance_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        try:
            with open(filename, 'w') as f:
                f.write("Student Attendance List\n")
                f.write(f"Data & Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                for student_id, (name, ip) in self.attendance.items():
                    f.write(f"{name}\t{student_id}\t{ip}\n")
            messagebox.showinfo("Success", f"Attendance exported to {filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export: {e}")

    def on_closing(self):
        self.running = False
        try:
            if hasattr(self, 'raw_socket'):
                self.raw_socket.ioctl(socket.SIO_RCVALL, socket.RCVALL_OFF)
                self.raw_socket.close()
        except:
            pass
        try:
            if hasattr(self, 'chat_socket'):
                self.chat_socket.close()
        except:
            pass
        try:
            if hasattr(self, 'p2p_socket'):
                self.p2p_socket.close()
        except:
            pass
        self.root.destroy()

if __name__ == "__main__":
    root = Tk()
    app = ServerApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()