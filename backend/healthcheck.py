"""Read-only Gunicorn readiness probe from the trusted loopback peer."""

from http.client import HTTPConnection
import os
import sys


def main():
    allowed = [host.strip() for host in os.environ.get('ALLOWED_HOSTS', '').split(',') if host.strip()]
    host = next((item.lstrip('.') for item in allowed if item != '*'), 'localhost')
    connection = HTTPConnection('127.0.0.1', 8000, timeout=5)
    try:
        # Gunicorn accepts this scheme only from its configured local proxy peers.
        connection.request('GET', '/proxy/health/', headers={
            'Host': host, 'X-Forwarded-Proto': 'https',
        })
        response = connection.getresponse()
        return 0 if response.status == 200 and response.read(32) == b'healthy\n' else 1
    except (OSError, ValueError):
        return 1
    finally:
        connection.close()


if __name__ == '__main__':
    sys.exit(main())
