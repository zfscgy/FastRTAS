import time
import numpy as np
from enum import Enum
from typing import Union, Callable
from FastRTAS.Core.Backends import NumpyBackend
from FastRTAS.Comm.Peer import Peer
from FastRTAS.Utils import parallel


class RTASException(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


_rtas_mode_val = 0

def _next_rtas_mode_val():
    global _rtas_mode_val
    _rtas_mode_val += 1
    return _rtas_mode_val


class RTASMode(Enum):
    Private = _next_rtas_mode_val()
    Public = _next_rtas_mode_val()
    Shared = _next_rtas_mode_val()


class RTASValue:
    def __init__(self, mode: RTASMode, value=None, owner=None, shape=None):
        self.mode = mode
        self.value = value
        self.owner = owner
        self.shape = shape


class RTAS:
    def __init__(self, addr_dict: dict, party_name: str, configs: dict=None):
        """
        :param addr_dict:
        :param party_name:
        :param configs:
                key                     default
                peer.init_time          1
                peer.timeout            3
                rtas.share_std          5
                rtas.cached_triples     128
        """
        addr_dict = addr_dict.copy()
        if {"P0", "P1", "P2"} > set(addr_dict.values()):
            raise RTASException("RTAS init: RTAS protocol requires P0, P1 and P2, but only have %s" % set(addr_dict.keys()))
        if party_name not in addr_dict.values():
            raise RTASException("RTAS init: Current player %s is not in the address dict" % party_name)
        self.addr_dict = addr_dict.copy()
        self.addr = [addr for addr in addr_dict if addr_dict[addr] == party_name][0]
        self.party = party_name

        del addr_dict[self.addr]

        if configs is None:
            configs = dict()

        self.peer = Peer(self.addr, addr_dict, configs.get("peer.timeout") or 3)
        time.sleep(configs.get("peer.init_time") or 1)
        self.peer.connect_all()

        self.share_std = configs.get("rtas.shard_std") or 5

        # For P0 and P1
        self.synced_prng = None
        # For P2
        self.np_backend = None

        self.cached_triples = configs.get("rtas.cached_triples") or 128
        self.triple_sources = dict()

    def set_up(self):
        """
        In the set-up phase, P0 and P1 will sync their pseudo-random generator
        :return:
        """
        if self.party == "P0":
            random_seed = np.random.random_integers(0, 1145141919810)
            self.synced_prng = np.random.default_rng(random_seed)
            self.peer.send("P1", "random_seed", random_seed)
        elif self.party == "P1":
            random_seed = self.peer.recv("P0", "random_seed")
            self.synced_prng = np.random.default_rng(random_seed)
        else:
            self.np_backend = NumpyBackend(self.share_std)

    def new_private(self, get_value, party="P0", shape=None):
        """
        :param get_value: A function to get the value. Example:
                lambda: np.random.normal(0, 1, [10])
                lambda: pd.read_csv("data.csv").values
        :param party: Tht party owns the value
        :param shape: The shape of the value
        :return:
        """
        if isinstance(party, str):
            party = [party]
        elif isinstance(party, list):
            pass
        else:
            raise RTASException("new_private: Party must be party name or list of party names, but get %s" % party)

        if self.party == party[0]:
            value = get_value()
            for other_party in party[1:]:
                self.peer.send(other_party, "new_private", value)
        elif self.party in party[1:]:
            value = self.peer.recv(party[0], "new_private")
        else:
            value = None
        return RTASValue(RTASMode.Private, value, party, shape)

    def new_public(self, get_value, creator="P0"):
        """
        One party generates the value, the send it to others

        :param get_value:
        :param creator:
        :return:
        """
        if self.party == creator:
            value = get_value()
            for party in self.addr_dict.values():
                if party != self.party:
                    self.peer.send(party, "new_public", value)
        else:
            value = self.peer.recv(creator, "new_public")

        return RTASValue(RTASMode.Public, value, [creator])

    def share(self, value: RTASValue):
        if value.mode != RTASMode.Private:
            raise RTASException("share: Can only share a private value")
        if isinstance(value.owner, list):
            owner = value.owner[0]
        else:
            owner = value.owner
        if self.party == owner:
            if not isinstance(value.value, np.ndarray):
                raise RTASException("share: Can only share a numpy value")
            if self.party in ["P0", "P1"]:
                if value.shape is None:
                    raise RTASException("P0/P1 cannot share a value without shape specified(for implicit sharing)")
                my_share = value.value + self.synced_prng.normal(0, self.share_std, value.shape)
            else:
                my_share = None
                shared_p0 = np.random.normal(0, self.share_std, value.shape)
                shared_p1 = value.value - shared_p0
                parallel(self.peer.send,
                         [("P0", "share", shared_p0), ("P1", "share", shared_p1)])
        else:
            if owner in ["P0", "P1"]:
                if self.party in ["P0", "P1"]:
                    my_share = - self.synced_prng.normal(0, self.share_std, value.shape)
                else:
                    my_share = None
            else:
                if self.party in ["P0", "P1"]:
                    my_share = self.peer.recv(owner, "share")
                else:
                    my_share = None

        return RTASValue(RTASMode.Shared, my_share, ["P0", "P1"])

    def reveal_to(self, x: RTASValue, party: str="P0"):
        if x.mode == RTASMode.Public:
            return x.value
        elif x.mode == RTASMode.Shared:
            if party in ["P0", "P1"]:
                if self.party == "P0":
                    other_party = "P1"
                else:
                    other_party = "P0"
                if self.party == party:
                    another_share = self.peer.recv(other_party, "another_share")
                    return x.value + another_share
                elif self.party in ["P0", "P1"]:
                    self.peer.send(other_party, "another_share")
                    return None
                else:
                    return None
            else:
                if self.party in ["P0", "P1"]:
                    self.peer.send(party, "share_of_" + self.party, x.value)
                    return None
                elif self.party == party:
                    shares = []

                    def recv(p: str):
                        shares.append(self.peer.recv(p, "share_of_" + p))
                    errs = parallel(recv, [("P0",), ("P1",)])
                    if errs:
                        raise RTASException("share: Send shares failed: %s" % errs)
                    return shares[0] + shares[1]
                else:
                    return None
        elif x.mode == RTASMode.Private:
            if party in x.owner:
                return x.value
            else:
                if self.party == x.owner[0]:
                    self.peer.send(party, "private_value", x.value)
                    return None
                elif self.party == party:
                    return self.peer.recv(x.owner[0], "private_value")
                else:
                    return None
        else:
            pass  # This code will never be reached

    def linear(self, x: RTASValue, y: RTASValue, func: Callable[[np.ndarray, np.ndarray], np.ndarray]) -> RTASValue:
        if x.mode == RTASMode.Public and y.mode == RTASMode.Public:
                # Initially, a owner of a public value is its creator
                # So the operation result of two public values' owner should be
                # the combination of the two public value's owner
                # Since they both contribute to the result
                return RTASValue(RTASMode.Public, func(x.value, y.value), list(set(x.owner) | set(y.owner)))
        elif x.mode == RTASMode.Public and y.mode == RTASMode.Private:
            if self.party in y.owner:
                return RTASValue(RTASMode.Private, func(x.value, y.value), y.owner)
            else:
                return RTASValue(RTASMode.Private, None, y.owner)
        elif x.mode == RTASMode.Private and y.mode == RTASMode.Public:
            if self.party in x.owner:
                return RTASValue(RTASMode.Private, func(x.value, y.value), x.owner)
            else:
                return RTASValue(RTASMode.Private, None, x.owner)
        elif x.mode == RTASMode.Private and y.mode == RTASMode.Private:
            if set(x.owner) != set(y.owner):
                raise RTASException("The owner of private values should be same, but is %s, %s" % (x.owner, y.owner))
            elif self.party in x.owner:
                return RTASValue(RTASMode.Private, func(x.value, y.value), x.owner)
            else:
                return RTASValue(RTASMode.Private, None, x.owner)
        elif (x.mode == RTASMode.Shared and y.mode == RTASMode.Private) or \
                (x.mode == RTASMode.Private and y.mode == RTASMode.Shared):
                raise RTASException("Linear operation of a shared value and a private value is not allowed")
        elif x.mode == RTASMode.Shared and  y.mode == RTASMode.Public:
            if self.party in ["P0", "P1"]:
                return RTASValue(RTASMode.Shared, func(x.value, y.value / 2), ["P0", "P1"])
            else:
                return RTASValue(RTASMode.Shared, None, ["P0", "P1"])
        elif x.mode == RTASMode.Public and y.mode == RTASMode.Shared:
            if self.party in ["P0", "P1"]:
                return RTASValue(RTASMode.Shared, func(x.value / 2, y.value), ["P0", "P1"])
            else:
                return RTASValue(RTASMode.Shared, None, ["P0", "P1"])
        elif x.mode == RTASMode.Shared and y.mode == RTASMode.Shared:
            if self.party in ["P0", "P1"]:
                return RTASValue(RTASMode.Shared, func(x.value, y.value), ["P0", "P1"])
            else:
                return RTASValue(RTASMode.Shared, None, ["P0", "P1"])
        else:
            pass  # This code will never be reached

    def product(self, x: RTASValue, y: RTASValue, func: Callable[[np.ndarray, np.ndarray], np.ndarray],
                shape_x: list=None, shape_y: list=None, triple_source: str=None):
        if x.mode == RTASMode.Public and y.mode == RTASMode.Public:
            return RTASValue(RTASMode.Public, func(x.value, y.value), list(set(x.owner)|set(y.owner)))
        elif x.mode == RTASMode.Private and y.mode == RTASMode.Public:
            if self.party in x.owner:
                return RTASValue(RTASMode.Private, func(x.value, y.value), x.owner)
            else:
                return RTASValue(RTASMode.Private, None, x.owner)
        elif x.mode == RTASMode.Public and y.mode == RTASMode.Private:
            if self.party in y.owner:
                return RTASValue(RTASMode.Private, func(x.value, y.value), y.owner)
            else:
                return RTASValue(RTASMode.Private, None, y.owner)
        elif x.mode == RTASMode.Private and y.mode == RTASMode.Private:
            if set(x.owner) != set(y.owner):
                raise RTASException("Cannot get product of two private value with different owner")
            elif self.party in x.owner:
                return RTASValue(RTASMode.Private, func(x.value, y.value), x.owner)
            else:
                return RTASValue(RTASMode.Private, None, x.owner)
        elif (x.mode == RTASMode.Private and y.mode == RTASMode.Shared) or \
                (x.mode == RTASMode.Shared and y.mode == RTASMode.Private):
            raise RTASException("Cannot get product of a private value and a shared value")
        elif x.mode == RTASMode.Shared and y.mode == RTASMode.Public:
            if self.party in ["P0", "P1"]:
                return RTASValue(RTASMode.Shared, func(x.value, y.value), ["P0", "P1"])
            else:
                return RTASValue(RTASMode.Shared, None, ["P0", "p1"])
        elif x.mode == RTASMode.Public and y.mode == RTASMode.Shared:
            if self.party in ["P0", "P1"]:
                return RTASValue(RTASMode.Shared, func(x.value, y.value), ["P0", "P1"])
            else:
                return RTASValue(RTASMode.Shared, None, ["P0", "P1"])
        elif x.mode == RTASMode.Shared and y.mode == RTASMode.Shared:
            shape_x = x.shape or shape_x
            shape_y = y.shape or shape_y
            if shape_x is None and shape_y is None:
                raise RTASException(
                    "product: shape must be specified, but either RTASValue.shape and shape_x/shape_y is None")

            # If cache is not initialized
            if self.party in ["P0", "P1"]:
                if self.triple_sources.get(triple_source) is None:
                    self.triple_sources[triple_source] = []
            elif self.party == "P2":
                if self.triple_sources.get(triple_source) is None:
                    self.triple_sources[triple_source] = 0

            # If cache is empty
            if self.party in ["P0", "P1"]:
                # If triple cache is empty, receive triples from P2
                if len(self.triple_sources[triple_source]) == 0:
                    triples = self.peer.recv("P2", "triples")
                    self.triple_sources[triple_source] += triples
            elif self.party == "P2":
                if self.triple_sources[triple_source] == 0:
                    triples_P0 = []
                    triples_P1 = []
                    for i in range(self.cached_triples):
                        triple_0, triple_1 = self.np_backend.get_product_triple(shape_x, shape_y, func)
                        triples_P0.append(triple_0)
                        triples_P1.append(triple_1)
                    errs = parallel(self.peer.send, [("P0", "triples", triples_P0), ("P1", "triples", triples_P1)])
                    if errs:
                        raise RTASException("product: send triples failed %s" % errs)
                    self.triple_sources[triple_source] = self.cached_triples

            # Fetch triple from cache
            if self.party in ["P0", "P1"]:
                current_triple = self.triple_sources[triple_source].pop()

            elif self.party == "P2":
                self.triple_sources[triple_source] -= 1

            # Perform product function
            if self.party in ["P0", "P1"]:
                u, v, w = current_triple
                x_sub_u = x.value - u
                y_sub_v = y.value - v
                x_sub_u_other = None
                y_sub_v_other = None

                def send_share(other: str):
                    self.peer.send(other, "X-U and Y-V", (x_sub_u, y_sub_v))

                def get_other_share(other: str):
                    global x_sub_u_other, y_sub_v_other
                    x_sub_u_other, y_sub_v_other = self.peer.recv(other, "X-U and Y-V")
                if self.party == "P0":
                    parallel([send_share, get_other_share], [("P1",), ("P1")])
                else:
                    parallel([send_share, get_other_share], [("P0",), ("P0")])

                x_sub_u += x_sub_u_other
                y_sub_v += y_sub_v_other

                if self.party == "P0":
                    return RTASValue(
                        RTASMode.Shared,
                        func(x_sub_u, y_sub_v) + func(u, y_sub_v) + func(x_sub_u, v) + w,
                        ["P0", "P1"])
                else:
                    return RTASValue(
                        RTASMode.Shared,
                        func(u, y_sub_v) + func(x_sub_u, v) + w,
                        ["P0", "P1"])
            else:
                return RTASValue(RTASMode.Shared, None, ["P0", "P1"])
        else:
            pass  # This code will never be reached
