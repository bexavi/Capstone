/**
 * Normalize assistant LaTeX-style delimiters so @nuxtjs/mdc + remark-math can render them.
 * Models often emit \\( ... \\) / \\[ ... \\]; remark-math expects $...$ / $$...$$.
 */
export function normalizeAssistantMathMarkdown(md: string): string {
  if (!md) {
    return md
  }
  let s = md
  s = s.replace(/\\\[([\s\S]*?)\\\]/g, (_, inner: string) => `\n\n$$\n${inner.trim()}\n$$\n\n`)
  s = s.replace(/\\\(([\s\S]*?)\\\)/g, (_, inner: string) => `$${inner.trim()}$`)
  return s
}
