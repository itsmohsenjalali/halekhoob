"""Defense in depth for the downloader. Deployment also blocks private IPs with systemd."""

import ipaddress
import socket

_getaddrinfo = socket.getaddrinfo
_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex


def is_public(value):
    address = ipaddress.ip_address(value.split("%")[0])
    if getattr(address, "ipv4_mapped", None):
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


def public_addresses(host, port, family=0, type=0, proto=0, flags=0):
    addresses = _getaddrinfo(host, port, family, type, proto, flags)
    if not addresses or any(not is_public(item[4][0]) for item in addresses):
        raise OSError("Private or reserved network addresses are blocked")
    return addresses


def install_network_guard():
    def connect(sock, address):
        if sock.family not in (socket.AF_INET, socket.AF_INET6):
            raise OSError("Only public internet connections are allowed")
        candidates = public_addresses(address[0], address[1], sock.family, sock.type)
        # Connect to the validated literal, not a hostname that can rebind after DNS validation.
        return _connect(sock, candidates[0][4])

    def connect_ex(sock, address):
        try:
            connect(sock, address)
            return 0
        except OSError as exc:
            return exc.errno or 13

    socket.getaddrinfo = public_addresses
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
