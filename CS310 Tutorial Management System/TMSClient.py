import socket
import struct
import threading
import random
import time
from tkinter import *
from tkinter import ttk
from tkinter import scrolledtext, messagebox, simpledialog

class StudentApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Student Client")
        self.root.geometry("600x500")
        self.p2p_lock = threading.Lock()
        self.p2p_connections = {}
        
        # NETWORK SETUP
        self.server_ip = '127.0.0.1'
        self.checkin_port = 5000    # USE PORT 5000 FOR CHECKIN
        self.chat_port = 5001       # PORT 5001 FOR GROUP CHAT
        self.p2p_port = 5002        # PORT FOR P2P 
        self.client_port = 1234
        self.my_p2p_port = random.randint(5050, 6050)
        self.running = True
        self.p2p_enabled = False
        self.p2p_connections = {}
        self.current_peer = None
        self.discussion_active = False
        
        # Get student info
        self.student_id, self.name = self.get_student_info()
        if not self.student_id or not self.name:
            self.root.destroy()
            return
            
        self.root.title(f"Student: {self.name} ({self.student_id})")
        self.create_widgets()
        self.start_network()

    # function to get student info in the UI
    def get_student_info(self):
        student_id = simpledialog.askstring("Student ID", "Enter Your Student ID:", parent=self.root)
        name = simpledialog.askstring("Name", "Enter Your Fullname:", parent=self.root)
        return student_id, name

    def create_widgets(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=BOTH, expand=True)
        
        # Check-in Tab
        self.checkin_tab = Frame(self.notebook)
        self.notebook.add(self.checkin_tab, text="Check-in")
        self.setup_checkin_tab()
        
        # Group Chat Tab
        self.chat_tab = Frame(self.notebook)
        self.notebook.add(self.chat_tab, text="Group Chat")
        self.setup_chat_tab()
        
        # P2P Chat Tab
        self.p2p_tab = Frame(self.notebook)
        self.notebook.add(self.p2p_tab, text="P2P Chat")
        self.setup_p2p_tab()
        
        # Discussion Timer
        self.time_label = Label(self.root, text="Discussion not started", fg="red", bd=1, relief=SUNKEN, anchor=W)
        self.time_label.pack(side=BOTTOM, fill=X)

    def setup_checkin_tab(self):
        Label(self.checkin_tab, text="Check-in Status", font=('Arial', 12, 'bold')).pack(pady=5)
        self.status_label = Label(self.checkin_tab, text="Not checked in", fg="red")
        self.status_label.pack(pady=5)
        Button(self.checkin_tab, text="Check In", command=self.send_checkin).pack(pady=10)

    def setup_chat_tab(self):
        self.chat_display = scrolledtext.ScrolledText(self.chat_tab, state='disabled')
        self.chat_display.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        msg_frame = Frame(self.chat_tab)
        msg_frame.pack(fill=X, padx=10, pady=5)
        self.message_entry = Entry(msg_frame)
        self.message_entry.pack(side=LEFT, fill=X, expand=True, padx=5)
        self.message_entry.bind("<Return>", lambda e: self.send_chat_message())
        Button(msg_frame, text="Send", command=self.send_chat_message).pack(side=RIGHT)

    def setup_p2p_tab(self):
        # Peer list
        self.peer_listbox = Listbox(self.p2p_tab, height=10)
        self.peer_listbox.pack(fill=BOTH, expand=True, padx=10, pady=5)
        self.peer_listbox.bind('<<ListboxSelect>>', self.select_peer)
        
        # P2P Chat display
        self.p2p_display = scrolledtext.ScrolledText(self.p2p_tab, state='disabled')
        self.p2p_display.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        # P2P Message frame
        p2p_msg_frame = Frame(self.p2p_tab)
        p2p_msg_frame.pack(fill=X, padx=10, pady=5)
        self.p2p_message_entry = Entry(p2p_msg_frame)
        self.p2p_message_entry.pack(side=LEFT, fill=X, expand=True, padx=5)
        self.p2p_message_entry.bind("<Return>", lambda e: self.send_p2p_message())
        Button(p2p_msg_frame, text="Send", command=self.send_p2p_message).pack(side=RIGHT)
        
        # Refresh button
        Button(self.p2p_tab, text="Refresh Peers", command=self.get_peer_list).pack(side=BOTTOM)
        
        # Auto-refresh peers every 5 seconds if discussion is active
        self.auto_refresh_peers()

    def auto_refresh_peers(self):
        if self.discussion_active and self.p2p_enabled:
            self.get_peer_list()
        self.root.after(5000, self.auto_refresh_peers)

    def start_network(self):
        # Raw socket for check-in
        try:
            self.raw_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_IP)
            self.raw_socket.bind((self.server_ip, self.client_port))
            self.raw_socket.ioctl(socket.SIO_RCVALL, socket.RCVALL_ON)
            threading.Thread(target=self.listen_for_responses, daemon=True).start()
        except PermissionError:
            messagebox.showerror("Error", "Please run as administrator")
            self.root.destroy()
            return
            
        # TCP socket for chat
        try:
            self.chat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.chat_socket.connect((self.server_ip, self.chat_port))
            self.chat_socket.send(f"REGISTER:{self.student_id}:{self.name}".encode())
            threading.Thread(target=self.listen_for_chat, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Error", f"Failed To Connect To Chat: {e}")
            self.root.destroy()
        
        # P2P listener socket
        self.p2p_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.p2p_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.p2p_listener.bind((self.server_ip, self.my_p2p_port))
        self.p2p_listener.listen(5)
        threading.Thread(target=self.listen_for_p2p, daemon=True).start()

    # Function to send checkin to the raw socket
    def send_checkin(self):
        payload = f"CHECKIN:{self.student_id}:{self.name}"
        try:
            packet = self.build_raw_packet(
                self.server_ip, self.server_ip,
                self.client_port, self.checkin_port,
                payload
            )
            self.raw_socket.sendto(packet, (self.server_ip, 0))
            self.status_label.config(text="Check-in sent", fg="orange")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to send check-in: {e}")

    # function to listen for responses from server.
    def listen_for_responses(self):
        while self.running:
            try:
                packet, addr = self.raw_socket.recvfrom(65535)
                if b"ACK:" in packet:
                    ack = packet.split(b"ACK:")[1].decode().split('\x00')[0].split(':')
                    if ack[0] == self.student_id:
                        self.status_label.config(text=f"Checked in at {ack[1]}", fg="green")
                        # If discussion is already active when checking in
                        if self.discussion_active:
                            self.register_p2p()
                elif b"START_DISCUSSION" in packet:
                    self.discussion_active = True
                    self.p2p_enabled = True
                    self.time_label.config(text="Discussion started - 30:00 remaining", fg="green")
                    self.register_p2p()
                    threading.Thread(target=self.discussion_timer, daemon=True).start()
                elif b"WARNING:" in packet:
                    warning = packet.split(b"WARNING:")[1].decode().split('\x00')[0]
                    self.log_message(f"\n[SYSTEM WARNING]: {warning}\n")
            except:
                if self.running:
                    pass

    def discussion_timer(self):
        start_time = time.time()
        while self.running and self.discussion_active:
            elapsed = time.time() - start_time
            remaining = max(0, 1800 - elapsed)  # 30 minutes = 1800 seconds
            mins, secs = divmod(remaining, 60)
            self.time_label.config(text=f"Discussion active - {int(mins)}:{int(secs):02d} remaining")
            
            if remaining <= 0:
                self.discussion_active = False
                self.p2p_enabled = False
                self.time_label.config(text="Discussion ended", fg="red")
                break
            time.sleep(1)
    # function to listen for messages from students
    def listen_for_chat(self):
        while self.running:
            try:
                data = self.chat_socket.recv(1024).decode()
                if not data:
                    break
                self.log_message(data)
            except:
                if self.running:
                    self.log_message("\n[Disconnected from server]\n")
                break

    def listen_for_p2p(self):
        while self.running:
            try:
                conn, addr = self.p2p_listener.accept()
                threading.Thread(target=self.handle_p2p_connection, args=(conn,), daemon=True).start()
            except:
                if self.running:
                    pass

    def handle_p2p_connection(self, conn):
        try:
            while self.running:
                data = conn.recv(1024).decode()
                if not data:
                    break
                
                if data.startswith("P2P_MSG:"):
                    _, sender_id, message = data.split(":", 2)
                    self.log_p2p_message(f"[{sender_id}]: {message}")
        except:
            pass
        finally:
            with self.p2p_lock:
                # Remove connection from dictionary if it exists
                for peer_id, peer_conn in list(self.p2p_connections.items()):
                    if peer_conn == conn:
                        del self.p2p_connections[peer_id]
                        break
            conn.close()

    def register_p2p(self):
        try:
            conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            conn.connect((self.server_ip, self.p2p_port))
            conn.send(f"REGISTER_P2P:{self.student_id}:{self.my_p2p_port}".encode())
            response = conn.recv(1024).decode()
            if response == "P2P_REGISTERED":
                self.log_message("\n[SYSTEM]: Registered for P2P communication\n")
            conn.close()
            # Get initial peer list
            self.get_peer_list()
        except Exception as e:
            self.log_message(f"\n[SYSTEM ERROR]: Failed to register P2P: {e}\n")

    def get_peer_list(self):
        if not self.p2p_enabled:
            return
            
        try:
            conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            conn.connect((self.server_ip, self.p2p_port))
            conn.send(f"GET_PEERS:{self.student_id}".encode())
            
            data = conn.recv(1024).decode()
            if data.startswith("PEER_LIST:"):
                peer_data = data.split(":")[1]
                if not peer_data:  # No peers available
                    self.peer_listbox.delete(0, END)
                    self.peer_listbox.insert(END, "No peers available")
                    return
                    
                peers = peer_data.split(",")
                self.peer_listbox.delete(0, END)
                for peer in peers:
                    try:
                        peer_id, peer_name, peer_port = peer.split("|")
                        self.peer_listbox.insert(END, f"{peer_name} ({peer_id}) - Port: {peer_port}")
                    except ValueError:
                        continue  # Skip malformed entries
            conn.close()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to get peer list: {str(e)}")
            if 'conn' in locals():
                conn.close()

    def select_peer(self, event):
        selection = event.widget.curselection()
        if selection:
            index = selection[0]
            selected_text = event.widget.get(index)
            if " - Port: " in selected_text:  # Only select valid peers
                self.current_peer = selected_text

    def send_p2p_message(self):
        if not self.current_peer or " - Port: " not in self.current_peer:
            messagebox.showwarning("Warning", "Please select a valid peer first")
            return
            
        message = self.p2p_message_entry.get().strip()
        if not message:
            return
            
        try:
            # Extract peer info from selection
            peer_info = self.current_peer.split(" - Port: ")
            peer_port = int(peer_info[1])
            peer_id = peer_info[0].split(" (")[1].rstrip(")")
            
            with self.p2p_lock:
                if peer_id in self.p2p_connections:
                    conn = self.p2p_connections[peer_id]
                else:
                    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    conn.connect((self.server_ip, peer_port))
                    self.p2p_connections[peer_id] = conn
                    
            conn.send(f"P2P_MSG:{self.student_id}:{message}".encode())
            self.log_p2p_message(f"You: {message}")
            self.p2p_message_entry.delete(0, END)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to send P2P message: {str(e)}")
            with self.p2p_lock:
                if peer_id in self.p2p_connections:
                    del self.p2p_connections[peer_id]

    # Function to manualy build packets
    def build_raw_packet(self, src_addr, dst_addr, src_port, dst_port, payload):
        # Build a TCP packet with proper headers
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

    def log_message(self, message):
        self.chat_display.config(state='normal')
        self.chat_display.insert(END, message + "\n")
        self.chat_display.config(state='disabled')
        self.chat_display.see(END)

    def log_p2p_message(self, message):
        self.p2p_display.config(state='normal')
        self.p2p_display.insert(END, message + "\n")
        self.p2p_display.config(state='disabled')
        self.p2p_display.see(END)

    def send_chat_message(self):
        message = self.message_entry.get().strip()
        if not message:
            return
            
        if message.lower() == '/exit':
            self.on_closing()
            return
            
        try:
            self.chat_socket.send(f"CHAT:{self.student_id}:{message}".encode())
            self.log_message(f"You: {message}")
            self.message_entry.delete(0, END)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to send message: {e}")

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
            if hasattr(self, 'p2p_listener'):
                self.p2p_listener.close()
        except:
            pass
        with self.p2p_lock:
            for conn in self.p2p_connections.values():
                try:
                    conn.close()
                except:
                    pass
            self.p2p_connections.clear()
        self.root.destroy()

if __name__ == "__main__":
    root = Tk()
    app = StudentApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()