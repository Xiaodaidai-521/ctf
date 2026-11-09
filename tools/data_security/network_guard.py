"""Test-only network fence. Real model, Docker and HTTP connections are forbidden."""
import os
import socket
import sys

_installed = False


def install():
    global _installed
    if _installed:
        return
    if os.environ.get('DATA_SECURITY_ISOLATED_TEST') != '1':
        raise RuntimeError('ISOLATED_TEST_OPT_IN_REQUIRED')
    port = int(os.environ['DS_TEST_PG_PORT'])
    directory = os.environ['DS_TEST_PG_SOCKET']
    if directory != '/home/hatch/workspace/ctf-data-security/.state/pg-run':
        raise RuntimeError('ISOLATED_SOCKET_REQUIRED')

    def guard(event, args):
        if event == 'socket.connect':
            sock, address = args
            allowed = (sock.family == socket.AF_UNIX and
                       address == directory + '/.s.PGSQL.' + str(port))
            if sock.family == socket.AF_INET and type(address) is tuple:
                allowed = address[0] == '127.0.0.1' and address[1] == port
            if not allowed:
                raise RuntimeError('TEST_EXTERNAL_NETWORK_FORBIDDEN')
        elif event == 'socket.getaddrinfo':
            if args[0] not in ('localhost', '127.0.0.1', None):
                raise RuntimeError('TEST_EXTERNAL_DNS_FORBIDDEN')

    sys.addaudithook(guard)
    _installed = True
