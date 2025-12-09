import socket
import time

HOST = '127.0.0.1'  
PORT = 50002

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
s.connect((HOST, PORT))

cmd = bytes([0xFE, 0xFE, 0xA4, 0xE0, 0x03, 0xFD])
print(f"→ {cmd.hex(' ').upper()}")
s.send(cmd)

for _ in range(10):
    response = bytearray()
    start = time.time()
    
    while time.time() - start < 2:
        byte = s.recv(1)
        if not byte:
            break
        response.extend(byte)
        if byte[0] == 0xFD:
            break
    
    if len(response) == 0:
        break
    
    print(f"← {response.hex(' ').upper()}")
    
    if len(response) >= 11 and response[4] in [0x00, 0x03, 0x05]:
        break

s.close()
