"""Isolated local scanner process; no Django, model client or execution service."""
import os
import sys
from pathlib import Path


def _resource_limits():
    if sys.platform == 'win32':
        import win32api
        import win32job

        job = win32job.CreateJobObject(None, '')
        limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
        basic = limits['BasicLimitInformation']
        basic['LimitFlags'] = (win32job.JOB_OBJECT_LIMIT_PROCESS_TIME
                               | win32job.JOB_OBJECT_LIMIT_PROCESS_MEMORY
                               | win32job.JOB_OBJECT_LIMIT_ACTIVE_PROCESS)
        basic['PerProcessUserTimeLimit'] = 3 * 10_000_000
        basic['ActiveProcessLimit'] = 1
        limits['ProcessMemoryLimit'] = 512 * 1024 * 1024
        win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
        win32job.AssignProcessToJobObject(job, win32api.GetCurrentProcess())
        return job  # Keep the native limits alive for the worker's lifetime.

    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _readonly_worker(event, args):
    if event == 'open':
        _, mode, flags = args
        if ((mode and any(marker in mode for marker in ('w', 'a', 'x', '+')))
                or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            raise PermissionError('SCANNER_WRITE_FORBIDDEN')
    elif (event.startswith('socket.') or event.startswith('subprocess.')
          or event in {'os.system', 'os.fork', 'os.forkpty', 'os.posix_spawn', 'os.exec',
                       'os.spawn', 'os.remove', 'os.rename', 'os.mkdir', 'os.rmdir',
                       'os.symlink', 'os.link', 'os.chmod', 'os.chown', 'os.utime'}):
        raise PermissionError('SCANNER_SIDE_EFFECT_FORBIDDEN')


if __name__ == '__main__':
    _native_job = _resource_limits()
    sys.addaudithook(_readonly_worker)
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    import json
    from data_lab.scanning import scan_registered

    try:
        request = json.loads(sys.stdin.read(4097))
        result = scan_registered(request)
    except Exception:
        result = {'error': 'PARSER_FAILED'}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))
