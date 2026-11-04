export function normalizeTrend(trend) {
  const dates = Array.isArray(trend?.dates) ? trend.dates : []
  const series = (key) => dates.map((_, index) => {
    const value = trend?.[key]?.[index]
    return typeof value === 'number' && Number.isFinite(value) ? value : null
  })
  return { dates, scores: series('scores'), theory_scores: series('theory_scores'), practice_scores: series('practice_scores') }
}

export function scoreTrendOption(trend, token) {
  const color = (name) => token(name).trim()
  const size = (name) => parseFloat(token(name))
  const textColor = color('--ink-secondary')
  const surface = color('--surface')
  const formatScore = (value) => value === null || value === undefined ? '—' : `${value}%`
  const series = [
    { name: '总分', key: 'scores', symbol: 'circle', type: 'solid' },
    { name: '理论', key: 'theory_scores', symbol: 'rect', type: 'dashed' },
    { name: '实战', key: 'practice_scores', symbol: 'triangle', type: 'dotted' },
  ]
  return {
    color: ['--series-1', '--series-2', '--series-3'].map(color),
    animationDuration: size('--motion-normal'),
    animationDurationUpdate: size('--motion-normal'),
    textStyle: { fontFamily: color('--font-family'), fontSize: size('--text-caption'), color: textColor },
    tooltip: { trigger: 'axis', confine: true, backgroundColor: surface, borderColor: color('--line'), textStyle: { color: color('--ink') }, valueFormatter: formatScore },
    legend: { data: series.map(item => item.name), bottom: 0, textStyle: { color: textColor } },
    grid: { left: size('--space-1'), right: size('--space-6'), top: size('--space-4'), bottom: size('--space-6'), containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: trend.dates, axisTick: { show: false }, axisLine: { lineStyle: { color: color('--line') } }, axisLabel: { color: textColor, hideOverlap: true } },
    yAxis: { type: 'value', name: '成绩', min: 0, max: 100, axisLabel: { color: textColor, formatter: '{value}%' }, splitLine: { lineStyle: { color: color('--line') } } },
    series: series.map(item => ({
      name: item.name, type: 'line', data: trend[item.key], connectNulls: false,
      symbol: item.symbol, symbolSize: size('--space-1'),
      lineStyle: { width: 2, type: item.type },
      itemStyle: { borderColor: surface, borderWidth: 2 },
      endLabel: { show: true, formatter: '{a}', color: textColor },
      labelLayout: { moveOverlap: 'shiftY' },
    })),
  }
}
