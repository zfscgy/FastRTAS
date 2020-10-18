import threading
import numpy as np
import time
from FastRTAS.Comm.Peer import Peer

passed = unpassed = 0

print("Test Peer:")

print("=====Test peer send")
try:
    p0 = Peer("127.0.0.1:8480", {"127.0.0.1:8481": "P1"})
    p1 = Peer("127.0.0.1:8481", {"127.0.0.1:8480": "P0"})
    p0.connect_all()
    p1.connect_all()
    np_sent = np.array([1, 2, 3])
    threading.Thread(target=p0.send, args=("P1", "Test", np_sent)).start()
    time.sleep(0.1)
    np_recvd = p1.recv("P0", "Test")
    p0.terminate()
    p1.terminate()
    if np.prod(np_recvd == np_sent) != 1:
        print("Send failed, expect %s but get %s" % (np_sent, np_recvd))
        unpassed += 1
    else:
        passed += 1
except Exception as e:
    print("Error:", e)

print("=================\nAll tests done, passed: %d, unpassed %d" % (passed, unpassed))