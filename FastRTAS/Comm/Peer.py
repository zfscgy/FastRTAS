import pickle
from FastRTAS.Comm.Socket import SocketServer


class PeerException(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


class PackedMessage:
    def __init__(self, header: str, obj: object):
        self.header = header
        self.obj = obj

    def serialize(self):
        return pickle.dumps(self)


class Peer(SocketServer):
    def __init__(self, address: str, other_addrs: dict, timeout=5):
        super(Peer, self).__init__(address, other_addrs, timeout)

    def send(self, peer_name: str, header: str, obj: object=None):
        self.send_to(peer_name, PackedMessage(header, obj).serialize())

    def recv(self, peer_name: str, header: str):
        data = self.recv_from(peer_name)
        packed_message = pickle.loads(data)
        if not isinstance(packed_message, PackedMessage):
            raise PeerException("Message corrupted or wrong message")
        if packed_message.header != header:
            raise PeerException("Message headers do not match: expect %s but get %s" % (header, packed_message.header))
        return packed_message.obj
