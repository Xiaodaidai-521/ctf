"""Metadata-only log boundary. Attach to output handlers, not just the root logger."""
import logging

from data_security.contracts import EventKind, ReasonCode


class SafeLogFilter(logging.Filter):
    def filter(self, record):
        # Never render msg/args, an exception, or an arbitrary extra object. Even
        # partial credentials split across log calls are dropped, not regex-masked.
        reason = record.__dict__.get('reason_code')
        reason = reason.value if type(reason) is ReasonCode else reason
        if type(reason) is not str or reason not in ReasonCode._value2member_map_:
            reason = ''
        kind = record.__dict__.get('event_kind')
        kind = kind.value if type(kind) is EventKind else kind
        if type(kind) is not str or kind not in EventKind._value2member_map_:
            kind = ''
        counts = record.__dict__.get('counts')
        counts = {name: value for name, value in counts.items()
                  if name in ('hit', 'processed', 'excluded', 'failed', 'unknown', 'unscanned', 'records', 'bytes')
                  and type(value) is int and 0 <= value <= 2**53 - 1} if type(counts) is dict else {}
        level = record.levelno if type(record.levelno) is int and record.levelno in (10, 20, 30, 40, 50) else 40
        message = 'LOG_EXCEPTION_OMITTED' if record.exc_info or record.exc_text else 'LOG_MESSAGE_OMITTED'
        # Idempotence when both a filter and the safe formatter are installed.
        if type(record.msg) is str and record.msg == 'LOG_EXCEPTION_OMITTED':
            message = record.msg
        clean = logging.LogRecord('application', level, '', 0, reason or message, (), None, func='')
        clean.threadName = ''
        clean.processName = ''
        clean.__dict__.update(reason_code=reason, event_kind=kind, counts=counts)
        record.__dict__.clear()
        record.__dict__.update(clean.__dict__)
        return True


class SafeLogFormatter(logging.Formatter):
    """Also sanitize at formatting time so cached exception text cannot escape."""
    def format(self, record):
        SafeLogFilter().filter(record)
        return super().format(record)


def install_safe_logging():
    handlers = set(logging.getLogger().handlers)
    for logger in logging.Logger.manager.loggerDict.values():
        if isinstance(logger, logging.Logger):
            handlers.update(logger.handlers)
    if not handlers:
        handler = logging.StreamHandler()
        logging.getLogger().addHandler(handler)
        handlers.add(handler)
    for handler in handlers:
        handler.addFilter(SafeLogFilter())
        handler.setFormatter(SafeLogFormatter('%(levelname)s %(message)s'))
