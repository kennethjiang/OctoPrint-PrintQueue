# coding=utf-8
from __future__ import absolute_import

def ip_addr():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        s.connect(('10.255.255.255', 1))
    except:
        s.connect(("8.8.8.8", 53))   # None of these 2 ways are 100%. Double them to maximize the chance

    primary_ip = s.getsockname()[0]
    s.close()

    return primary_ip
