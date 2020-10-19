import time

import numpy as np
from FastRTAS.Utils import parallel
from FastRTAS.Core.RTAS import RTAS


passed = unpassed = 0

print("Test RTAS:")

print("=====Test setup")
parties = dict()
try:
    def rtas_share_test(party: str):
        rtas = RTAS({"127.0.0.1:4900": "P0", "127.0.0.1:4901": "P1", "127.0.0.1:4902": "P2"}, party)
        # Notice: Must sleep to wait all rtas connected
        time.sleep(1)
        rtas.set_up()
        parties[party] = rtas

    errs = parallel(rtas_share_test, [("P0",), ("P1",), ("P2",)])
    if errs is not None:
        print("Errors:", errs)
        unpassed += 1
    else:
        passed += 1
except Exception as e:
    print("Error:", e)
    unpassed += 1

print("=====Test private P0")
try:
    priv_val_P0 = np.random.normal(0, 1, [3])
    private_vals_P0 = dict()

    def rtas_new_private(party_name: str):
        rtas = parties[party_name]
        private_vals_P0[party_name] = rtas.new_private(lambda: priv_val_P0)

    errs = parallel(rtas_new_private, [("P0",), ("P1",), ("P2",)])
    if errs is not None:
        print("Errors: ", errs)
        unpassed += 1
    else:
        if private_vals_P0["P1"].value is not None or private_vals_P0["P2"].value is not None:
            print("Private values must be None for non-owners. But get %s and %s for party 1, 2"
                  % (private_vals_P0["P1"].value, private_vals_P0["P2"].value))
            unpassed +=1
        else:
            passed += 1
except Exception as e:
    print("Error:", e)
    unpassed += 1


print("=====Test public P2")
try:
    pub_val_P2 = np.array([1, 2, 3])
    public_vals_P2 = dict()
    def rtas_new_public(party_name: str):
        rtas = parties[party_name]
        public_vals_P2[party_name] = rtas.new_public(lambda: pub_val_P2, "P2")
    errs = parallel(rtas_new_public, [("P0",), ("P1",), ("P2",)])
    if errs is not None:
        print("Errors:", errs)
    else:
        if np.array_equal(public_vals_P2["P0"].value, public_vals_P2["P1"].value) and \
                np.array_equal(public_vals_P2["P0"].value, public_vals_P2["P2"].value):
            passed += 1
        else:
            print("Public value shoud be equal on all parties, but is %s" % public_vals_P2)
            unpassed += 1
except Exception as e:
    print("Error:", e)
    unpassed += 1


print("=====Test share private P0")
try:
    to_be_shared_P0 = np.random.normal(0, 1, [3])
    shared_vals_P0 = dict()

    def rtas_share_private(party_name: str):
        rtas = parties[party_name]
        private_val = rtas.new_private(lambda: to_be_shared_P0, shape=to_be_shared_P0.shape)
        shared_vals_P0[party_name] = rtas.share(private_val)
    errs = parallel(rtas_share_private, [("P0",), ("P1",), ("P2",)])
    if errs is not None:
        print("Errors:", errs)
        unpassed += 1
    else:
        summed = shared_vals_P0["P0"].value + shared_vals_P0["P1"].value
        if not np.allclose(to_be_shared_P0, summed):
            print("Expect shared values' sum is the raw value %s, but is %s" % (to_be_shared_P0, summed))
            unpassed += 1
        else:
            passed += 1
except Exception as e:
    print("Error:", e)
    unpassed += 1


print("=====Test share private P2")
try:
    to_be_shared_P2 = np.random.normal(0, 1, [3])
    shared_vals_P2 = dict()

    def rtas_share_private(party_name: str):
        rtas = parties[party_name]
        private_val = rtas.new_private(lambda: to_be_shared_P2, shape=to_be_shared_P2.shape)
        shared_vals_P2[party_name] = rtas.share(private_val)

    errs = parallel(rtas_share_private, [("P0",), ("P1",), ("P2",)])
    if errs is not None:
        print("Errors:", errs)
        unpassed += 1
    else:
        summed = shared_vals_P2["P0"].value + shared_vals_P2["P1"].value
        if not np.allclose(to_be_shared_P2, summed):
            print("Expect shared values' sum is the raw value %s, but is %s" % (to_be_shared_P2, summed))
            unpassed += 1
        else:
            passed += 1
except Exception as e:
    print("Error:", e)
    unpassed += 1


print("=====Test reveal private(P0) to P2")
try:
    revealed_vals_P2_from_P0 = dict()

    def rtas_reveal(party_name: str):
        rtas = parties[party_name]
        revealed_vals_P2_from_P0[party_name] = rtas.reveal_to(private_vals_P0[party_name], "P2")

    errs = parallel(rtas_reveal, [("P0",), ("P1",), ("P2",)])
    if errs is not None:
        print("Errors:", errs)
        unpassed += 1
    else:
        if np.allclose(revealed_vals_P2_from_P0["P2"], priv_val_P0):
            if revealed_vals_P2_from_P0["P0"] is None and revealed_vals_P2_from_P0["P1"] is None:
                passed += 1
            else:
                print("P0 and P1 should only get None")
                unpassed += 1
        else:
            print("Expect revealed value is the raw value %s, but is %s" % (revealed_vals_P2_from_P0["P2"], priv_val_P0))
            unpassed += 1

except Exception as e:
    print("Error:", e)
    unpassed += 1


print("=====Test reveal shared to P2")
try:
    revealed_vals_P2_from_shared_P0 = dict()

    def rtas_reveal(party_name: str):
        rtas = parties[party_name]
        revealed_vals_P2_from_shared_P0[party_name] = rtas.reveal_to(shared_vals_P0[party_name], "P2")

    errs = parallel(rtas_reveal, [("P0",), ("P1",), ("P2",)])
    if errs is not None:
        print("Errors:", errs)
        unpassed += 1
    else:
        if np.allclose(revealed_vals_P2_from_shared_P0["P2"], to_be_shared_P0):
            if revealed_vals_P2_from_shared_P0["P0"] is None and revealed_vals_P2_from_shared_P0["P1"] is None:
                passed += 1
            else:
                print("P0 and P1 should only get None")
                unpassed += 1
        else:
            print("Expect revealed value is the raw value %s, but is %s" %
                  (revealed_vals_P2_from_shared_P0["P2"], to_be_shared_P0))
            unpassed += 1

except Exception as e:
    print("Error:", e)
    unpassed += 1


print("=====Test linear shared public")
try:
    sum_of_shared_P2_and_pub_P2 = dict()

    def linear_add(party_name: str):
        rtas = parties[party_name]
        added = rtas.linear(shared_vals_P2[party_name], public_vals_P2[party_name], np.add)
        sum_of_shared_P2_and_pub_P2[party_name] = added

    errs = parallel(linear_add, [("P0",), ("P1",), ("P2",)])
    if errs is not None:
        print("Errors:", errs)
        unpassed += 1
    else:
        summed = sum_of_shared_P2_and_pub_P2["P0"].value + sum_of_shared_P2_and_pub_P2["P1"].value
        if np.allclose(summed, to_be_shared_P2 + pub_val_P2):
            passed += 1
        else:
            print("Sum of shared value shoule be %s but is %s" % (summed, to_be_shared_P2 + pub_val_P2))
            unpassed += 1

except Exception as e:
    print("Error:", e)
    unpassed += 1

for party in parties.values():
    party.peer.terminate()

print("=================\nAll tests done, passed: %d, unpassed %d" % (passed, unpassed))