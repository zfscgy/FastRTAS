import socket
import threading
from FastRTAS.Utils import parallel


class SocketException(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


def read_socket(s: socket.socket) -> bytes:
    try:
        len_bytes = s.recv(4)
        content_len = int.from_bytes(len_bytes, byteorder='big')
        content = s.recv(content_len)
        return content

    except:
        raise SocketException("Socket read error")


def write_socket(s: socket.socket, content: bytes):
    try:
        len_bytes = len(content).to_bytes(4, 'big')
        s.send(len_bytes + content)

    except:
        raise SocketException("Socket send error")


class SocketServer:
    def __init__(self, address: str, other_addrs: dict, timeout=5):
        """
        :param address:
        :param other_addrs: dict[address, name]
        :param timeout:
        """
        self.addr = address
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            ipv4, port = address.split(":")
            port = int(port)

        except:
            raise SocketException("Address %s not valid" % address)

        self.socket.bind((ipv4, port))
        socket.setdefaulttimeout(timeout)
        self.other_addrs = other_addrs
        self.other_recv_sockets = dict()
        self.other_send_sockets = dict()
        self.listening = True

        self.listen_thread = threading.Thread(target=self._listen_loop)
        self.listen_thread.start()

    def _listen_loop(self):
        self.socket.listen()
        not_connected_others = set(self.other_addrs.keys())
        while self.listening:
            try:
                accpeted_socket, addr = self.socket.accept()
            except TimeoutError as e:
                continue

            try:
                claimed_addr = str(read_socket(accpeted_socket), "utf-8")
            except TimeoutError:
                raise SocketException("Did not receive address claim after connection from %s" % addr)

            if claimed_addr.split(":")[0] != addr[0]:
                raise SocketException("Claimed Address %s do not match with the actual send address %s"
                                      % (claimed_addr, addr[0]))
            if claimed_addr in self.other_addrs:
                self.other_recv_sockets[self.other_addrs[claimed_addr]] = accpeted_socket
            else:
                raise SocketException("Get unexpected socket connection from %s" % addr)

            not_connected_others.remove(claimed_addr)
            if len(not_connected_others) == 0:
                break
        self.listening = False

    def connect_all(self):
        def connect_one(peer_addr: str, peer_name: str):
            my_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                peer_ipv4, peer_port = peer_addr.split(":")
                peer_port = int(peer_port)
            except:
                raise SocketException("%s is not a valid address" % peer_addr)

            try:
                my_socket.connect((peer_ipv4, peer_port))
                write_socket(my_socket, self.addr.encode("utf-8"))
            except TimeoutError:
                raise SocketException("Connect to %s: %s failed" % (peer_name, peer_addr))
            self.other_send_sockets[peer_name] = my_socket

        peers = [(peer_addr, self.other_addrs[peer_addr]) for peer_addr in self.other_addrs]
        parallel(connect_one, peers)

    def send_to(self, name: str, data: bytes):
        if name not in self.other_send_sockets:
            raise SocketException("Peer name %s dose not exist or not connected yet" % name)
        s = self.other_send_sockets[name]
        write_socket(s, data)

    def recv_from(self, name):
        if name not in self.other_recv_sockets:
            raise SocketException("Peer name %s dose not exist or not connected yet" % name)
        s = self.other_recv_sockets[name]
        return read_socket(s)

    def terminate(self):
        self.socket.close()
        for peer_name in self.other_send_sockets:
            self.other_send_sockets[peer_name].close()
        for peer_name in self.other_recv_sockets:
            self.other_recv_sockets[peer_name].close()
