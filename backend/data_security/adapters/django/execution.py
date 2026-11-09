"""Run synchronous ports off the event loop; release worker-owned DB connections."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from django.db import connections


def _execute(operation, *args):
    try:
        return operation(*args)
    finally:
        connections.close_all()


async def run_port(operation, *args):
    return await asyncio.to_thread(_execute, operation, *args)


def call_port(operation, *args):
    """Keep synchronous content builders usable from an async business entry."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return operation(*args)
    with ThreadPoolExecutor(max_workers=1) as worker:
        return worker.submit(_execute, operation, *args).result()
