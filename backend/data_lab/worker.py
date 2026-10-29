"""Isolated local scanner process; no Django, model client or execution service."""
import resource
import sys
from pathlib import Path

resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
from data_lab.scanning import scan_registered

if __name__ == '__main__':
    try:
        request = json.loads(sys.stdin.read(4097))
        result = scan_registered(request)
    except Exception:
        result = {'error': 'PARSER_FAILED'}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))
