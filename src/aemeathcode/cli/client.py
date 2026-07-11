import socket
import json

# 5 个测试用例:1 个正常 + 4 种异常,验证 server 的响应和健壮性
tests = [
    ('正常 ping',        b'{"jsonrpc":"2.0","id":"1","method":"ping","params":{}}\n'),
    ('烂 JSON (解析错)',  b'this is not json\n'),
    ('未知 method',      b'{"jsonrpc":"2.0","id":"2","method":"foobar","params":{}}\n'),
    ('id 是整数 (校验错)', b'{"jsonrpc":"2.0","id":3,"method":"ping","params":{}}\n'),
    ('省略 params',      b'{"jsonrpc":"2.0","id":"4","method":"ping"}\n'),
    ('运行 run',         json.dumps({
        "jsonrpc": "2.0", "id": "5", "method": "run",
        "params": {"goal": "读一下 /home/administrator/cc_learn/AemeathCode/CLAUDE.md,告诉我这个项目是干嘛的"},
    }).encode() + b'\n'),
]

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(('127.0.0.1', 9999))

# 一次性把 5 条请求都发出去
for _, payload in tests:
    s.sendall(payload)

# 收 5 条响应(按 \n 分帧),逐条打印
buffer = b""
got = 0
while got < len(tests):
    byte = s.recv(1024)
    if byte == b'':
        break
    buffer += byte
    while b"\n" in buffer:
        line, buffer = buffer.split(b"\n", 1)
        text = line.decode("utf-8")
        print(f"[{tests[got][0]}] -> {json.loads(text)}")
        got += 1

s.close()
