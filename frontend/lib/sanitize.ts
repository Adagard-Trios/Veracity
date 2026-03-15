import DOMPurify from 'dompurify';

/**
 * Sanitize any string before it touches the DOM.
 * Use this on ALL text sourced from agent outputs before
 * passing to chart labels, table cells, or rendered text.
 */
export function sanitize(input: string): string {
  if (typeof window === 'undefined') {
    // Server-side: strip all tags with a simple regex fallback
    return input.replace(/<[^>]*>/g, '').slice(0, 1000);
  }
  return DOMPurify.sanitize(input, { ALLOWED_TAGS: [], ALLOWED_ATTR: [] });
}
