import threading
from FastRTAS.Comm.Socket import SocketServer


passed = unpassed = 0

print("Test socket:")

print("=====Test create socket")
try:
    p0 = SocketServer("127.0.0.1:8480", {"127.0.0.1:8481": "P1"})
    p1 = SocketServer ("127.0.0.1:8481", {"127.0.0.1:8480": "P0"})
    passed += 1
except Exception as e:
    print("Error:",  e)
    unpassed += 1

print("=====Test connect socket")
try:
    p0.connect_all()
    p1.connect_all()
    passed += 1
except Exception as e:
    print("Error:", e)
    unpassed += 1

print("=====Test send&recv 1")
try:
    send_str = "Hello from P0"
    threading.Thread(target=p0.send_to, args=("P1", send_str.encode('utf-8'))).start()
    recv_str = str(p1.recv_from("P0"), 'utf-8')
    if send_str == recv_str:
        passed += 1
    else:
        print("Error: strings %s and %s do not match" % (send_str, recv_str))
        unpassed += 1
except Exception as e:
    print("Error:", e)
    unpassed += 1


print("=====Test send&recv 2")
try:
    send_str = "Hello from P1"
    threading.Thread(target=p1.send_to, args=("P0", send_str.encode('utf-8'))).start()
    recv_str = str(p0.recv_from("P1"), 'utf-8')
    if send_str == recv_str:
        passed += 1
    else:
        print("Error: strings %s and %s do not match" % (send_str, recv_str))
        unpassed += 1
except Exception as e:
    print("Error:", e)
    unpassed += 1

print("=====Test terminate")
try:
    p0.terminate()
    p1.terminate()
    passed += 1
except Exception as e:
    print("Error:", e)
    unpassed += 1

print("=================\nAll tests done, passed: %d, unpassed %d" % (passed, unpassed))
