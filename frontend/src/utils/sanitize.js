import DOMPurify from 'dompurify'

export function sanitizeHtml(value) {
  return DOMPurify.sanitize(value || '', {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ['style', 'iframe', 'object', 'embed', 'form'],
  })
}
