"""Shared metric envelope; missing observations are never imputed as zero."""


def metric(numerator, denominator, missing=0, *, status=None, window=None,
           versions=None, source='formal'):
    if denominator < 0 or missing < 0:
        raise ValueError('指标分母与缺失量不能为负数。')
    value = None if not denominator or numerator is None else numerator / denominator
    return {
        'numerator': numerator,
        'denominator': denominator,
        'missing': missing,
        'value': value,
        'status': status or ('not_connected' if not denominator and missing else
                             'no_data' if not denominator else
                             'partial' if missing else 'available'),
        'window': window or {'start': None, 'end': None},
        'versions': versions or {},
        'source': source,
    }


SOURCE_STATUS = {
    'module3': 'not_connected',
    'module4': 'not_connected',
    'module5': 'not_connected',
    'execution': 'not_started',
    'actual_protection': 'not_evaluated',
}
