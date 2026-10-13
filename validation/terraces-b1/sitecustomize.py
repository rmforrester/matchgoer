"""Validation-only: deny Python network connections outside isolated loopback."""
import socket
_connect=socket.socket.connect;_connect_ex=socket.socket.connect_ex
def allowed(address):
    if not isinstance(address,tuple):return  # local Unix-domain sockets
    if address[0] not in ('127.0.0.1','localhost','::1'):
        raise RuntimeError('Validation denies external network connections')
def connect(self,address):allowed(address);return _connect(self,address)
def connect_ex(self,address):allowed(address);return _connect_ex(self,address)
socket.socket.connect=connect;socket.socket.connect_ex=connect_ex
