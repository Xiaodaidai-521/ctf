"""Keep fixture values and exception messages out of regression evidence."""
import json
import logging
import traceback
import unittest

from django.test.runner import DiscoverRunner


class SafeResult(unittest.TextTestResult):
    def getDescription(self, test):
        return test.id()

    def _exc_info_to_string(self, err, test):
        kind, value, tb = err
        return json.dumps({
            'exception_type': kind.__name__,
            'frames': [{'file': frame.filename, 'line': frame.lineno, 'function': frame.name}
                       for frame in traceback.extract_tb(tb)],
            'message': 'omitted: fixture-safe evidence',
        }, ensure_ascii=False)

    def stopTest(self, test):
        self._mirrorOutput = False
        super().stopTest(test)


class IsolatedRunner(DiscoverRunner):
    def __init__(self, **kwargs):
        kwargs['buffer'] = True
        super().__init__(**kwargs)

    def get_resultclass(self):
        return SafeResult

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        from .network_guard import install
        install()
        # assertLogs installs its own handler; ordinary application logs are discarded.
        for logger in [logging.getLogger(), *[
            item for item in logging.Logger.manager.loggerDict.values()
            if isinstance(item, logging.Logger)
        ]]:
            logger.handlers = [logging.NullHandler()]
