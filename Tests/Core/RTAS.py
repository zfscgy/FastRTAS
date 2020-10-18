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

print("=====Test new_private")
try:
    private_vals = dict()

    def rtas_new_private(party_name: str):
        rtas = parties[party_name]
        private_vals[party_name] = rtas.new_private(lambda: np.random.normal(0, 1, [10]))

    errs = parallel(rtas_new_private, [("P0",), ("P1",), ("P2",)])
    if errs is not None:
        print("Errors: ", errs)
        unpassed += 1
    else:
        if private_vals["P1"].value is not None or private_vals["P2"].value is not None:
            print("Private values must be None for non-owners. But get %s and %s for party 1, 2"
                  % (private_vals["P1"].value, private_vals["P2"].value))
            unpassed +=1
        else:
            passed += 1
except Exception as e:
    print("Error:", e)
    unpassed += 1

print("=====Test new_public")
try:
    public_vals = dict()
    def rtas_new_public(party_name: str):
        rtas = parties[party_name]
        public_vals[party_name] = rtas.new_public(lambda: np.array([1, 2, 3]), "P2")
    errs = parallel(rtas_new_public, [("P0",), ("P1",), ("P2",)])
    if errs is not None:
        print("Errors:", errs)
    else:
        if np.array_equal(public_vals["P0"].value, public_vals["P1"].value) and \
                np.array_equal(public_vals["P0"].value, public_vals["P2"].value):
            passed += 1
        else:
            print("Public value shoud be equal on all parties, but is %s" % public_vals)
            unpassed += 1
except Exception as e:
    print("Error:", e)
    unpassed += 1


print("=====Test share private P0")
try:
    shared_vals_0 = dict()
    priv_val_0 = np.random.normal(0, 1, [10])
    def rtas_share_private(party_name: str):
        rtas = parties[party_name]
        private_val = rtas.new_private(lambda: priv_val_0, shape=priv_val_0.shape)
        shared_vals_0[party_name] = rtas.share(private_val)
    errs = parallel(rtas_share_private, [("P0",), ("P1",), ("P2",)])
    if errs is not None:
        print("Errors:", errs)
        unpassed += 1
    else:
        summed = shared_vals_0["P0"].value + shared_vals_0["P1"].value
        if not np.allclose(priv_val_0, summed):
            print("Expect shared values' sum is the raw value %s, but is %s" % (priv_val_0, summed))
            unpassed += 1
        else:
            passed += 1
except Exception as e:
    print("Error:", e)
    unpassed += 1

print("=====Test share private P2")
try:
    shared_vals_1 = dict()
    priv_val_1 = np.random.normal(0, 1, [10])
    def rtas_share_private(party_name: str):
        rtas = parties[party_name]
        private_val = rtas.new_private(lambda: priv_val_0, shape=priv_val_0.shape)
        shared_vals_0[party_name] = rtas.share(private_val)
    errs = parallel(rtas_share_private, [("P0",), ("P1",), ("P2",)])
    if errs is not None:
        print("Errors:", errs)
        unpassed += 1
    else:
        summed = shared_vals_1["P0"].value + shared_vals_1["P1"].value
        if not np.allclose(priv_val_1, summed):
            print("Expect shared values' sum is the raw value %s, but is %s" % (priv_val_1, summed))
            unpassed += 1
        else:
            passed += 1
except Exception as e:
    print("Error:", e)
    unpassed += 1


for party in parties.values():
    party.peer.terminate()

print("=================\nAll tests done, passed: %d, unpassed %d" % (passed, unpassed))