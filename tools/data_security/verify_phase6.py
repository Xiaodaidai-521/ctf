"""Phase-six evidence destination; retain the original default/bound test commands."""
from tools.data_security.verify_phase5 import main


if __name__ == '__main__':
    raise SystemExit(main(phase=6))
