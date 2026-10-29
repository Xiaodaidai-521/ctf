// Python locations are Unicode codepoints, never JavaScript UTF-16 offsets.
export function splitCodepoints(text, span) {
  const chars = Array.from(text || '')
  if (!span || !Number.isInteger(span.start) || !Number.isInteger(span.end) ||
      span.start < 0 || span.end <= span.start || span.end > chars.length) {
    return { before: chars.join(''), selected: '', after: '' }
  }
  return {
    before: chars.slice(0, span.start).join(''),
    selected: chars.slice(span.start, span.end).join(''),
    after: chars.slice(span.end).join(''),
  }
}
