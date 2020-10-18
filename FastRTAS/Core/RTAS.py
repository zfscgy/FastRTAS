import time
import numpy as np
from enum import Enum
from typing import Union, Callable

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

        self.share_std = configs.get("protocol.shard_std") or 5
        self.synced_prng = None

    def set_up(self):
        """
        In the set-up phase, P0 and P1 will
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
            pass

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

        return RTASValue(RTASMode.Public, value, creator)

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
                    self.peer.send(party, "share_of_" + self.party)
                    return None
                elif self.party == party:
                    shares = []

                    def recv(p: str):
                        shares.append(self.peer.recv(p, "share_of_" + p))

                    parallel(recv, [("P0",), ("P1",)])
                    return shares[0] + shares[1]
                else:
                    return None
        elif x.mode == RTASMode.Private:
            if party == x.owner:
                return x.value
            else:
                if self.party == x.owner:
                    self.peer.send(party, "private_value", x.value)
                    return None
                elif self.party == party:
                    return self.peer.recv(x.owner, "private_value")
                else:
                    return None
        else:
            pass  # This code will never be reached

    def linear(self, x: RTASValue, y: RTASValue, func: Callable[[np.ndarray, np.ndarray], np.ndarray]) -> RTASValue:
        res_mode = RTASMode.Shared
        my_share = None
        res_owner = ["P0", "P1"]
        if x.mode == RTASMode.Shared:
            if y.mode == RTASMode.Shared:
                if self.party in ["P0", "P1"]:
                    my_share = func(x.value, y.value)
                else:
                    my_share = None
            elif y.mode == RTASMode.Public:
                if self.party in ["P0", "P1"]:
                    my_share = func(x.value, y.value / 2)
                else:
                    my_share = None
            elif y.mode == RTASMode.Private:
                raise RTASException("Linear operation of a shared value and a private value is not allowed")
            else:
                pass  # This code will never be reached
        elif x.mode == RTASMode.Public:
            if y.mode == RTASMode.Shared:
                if self.party in ["P0", "P1"]:
                    my_share = func(x.value / 2, y.value)
                else:
                    my_share = None
            elif y.mode == RTASMode.Public:
                res_mode = RTASMode.Public
                my_share = func(x.value, y.value)

                # Initially, a owner of a public value is its creator
                # So the operation result of two public values' owner should be
                # the combination of the two public value's owner
                # Since they both contribute to the result
                if x.owner == y.owner:
                    res_owner = x.owner
                else:
                    res_owner = [x.owner, y.owner]
            elif y.mode == RTASMode.Private:
                if self.party == y.owner:
                    my_share = func(x.value, y.value)
                else:
                    my_share = None
            else:
                pass  # This code will never be reached
        elif x.mode == RTASMode.Private:
            res_mode = RTASMode.Private
            if y.mode == RTASMode.Shared:
                raise RTASException("Linear operation of a shared value and a private value is not allowed")
            elif y.mode == RTASMode.Public:
                if self.party == x.owner:
                    my_share = func(x.value, y.value)
                else:
                    my_share = None
            elif y.mode == RTASMode.Private:
                if x.owner != y.owner:
                    raise RTASException("The owner of private values should be same, but is %s, %s" % (x.owner, y.owner))
                elif self.party == x.owner:
                    my_share = func(x.value, y.value)
                else:
                    my_share = None
            else:
                pass  # This code will never be reached
        else:
            pass  # This code will never be reached
        return RTASValue(res_mode, my_share, res_owner)