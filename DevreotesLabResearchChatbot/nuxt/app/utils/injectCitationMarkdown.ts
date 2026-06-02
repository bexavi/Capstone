function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** For double-quoted HTML attributes (data-tooltip, aria-label). */
function escapeAttr(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
}

function tooltipForRefs(
  nums: number[],
  sPrefix: boolean[],
  sources?: string[]
): string {
  return nums
    .map((n, i) => {
      const label = sources?.[n - 1]?.trim() || `Source ${n}`
      const p = sPrefix[i] ? 'S' : ''
      return `[${p}${n}] ${label}`
    })
    .join(' · ')
}

function injectBracketCitations(text: string, sources?: string[]): string {
  return text.replace(/\[(S\d+(?:,\s*S\d+)*)\]|\[(\d+(?:,\s*\d+)*)\]/g, (full, sGrp: string | undefined, nGrp: string | undefined) => {
    if (sGrp) {
      const nums = sGrp.split(/,\s*/).map(s => Number.parseInt(s.replace(/^S/i, ''), 10))
      const tt = tooltipForRefs(nums, nums.map(() => true), sources)
      return `<span class="devreotes-cite" tabindex="0" data-tooltip="${escapeAttr(tt)}" aria-label="${escapeAttr(tt)}">${escapeHtml(full)}</span>`
    }
    const nums = nGrp!.split(/,\s*/).map(s => Number.parseInt(s, 10))
    const tt = tooltipForRefs(nums, nums.map(() => false), sources)
    return `<span class="devreotes-cite" tabindex="0" data-tooltip="${escapeAttr(tt)}" aria-label="${escapeAttr(tt)}">${escapeHtml(full)}</span>`
  })
}

/**
 * List lines like "- Foo ... 1, 7." when the model omits brackets (see backend prompt for [n]).
 */
function injectBulletPlainCitations(text: string, sources?: string[]): string {
  return text
    .split('\n')
    .map((line) => {
      if (line.includes('devreotes-cite')) {
        return line
      }
      if (!/^(\s*-\s+)/.test(line)) {
        return line
      }
      const end = /(\s+)(\d{1,2}(?:,\s*\d{1,2})+)(\s*[.!?])?$/
      const m = line.match(end)
      if (!m) {
        return line
      }
      const body = line.slice(0, line.length - m[0].length)
      if (!body.trim()) {
        return line
      }
      const ws = m[1]
      const numPart = m[2]
      const punct = m[3]
      if (!ws || !numPart) {
        return line
      }
      const nums = numPart.split(/,\s*/).map(Number)
      const raw = (ws + numPart + (punct || '')).trim()
      const tt = tooltipForRefs(nums, nums.map(() => false), sources)
      const span = `<span class="devreotes-cite" tabindex="0" data-tooltip="${escapeAttr(tt)}" aria-label="${escapeAttr(tt)}">${escapeHtml(raw)}</span>`
      return body + span + (punct || '')
    })
    .join('\n')
}

/**
 * Wraps bracketed / list-suffix citations in inline HTML so markdown stays a single document
 * and references get distinct styling plus a fast CSS tooltip (`data-tooltip`, no browser title delay).
 */
export function injectCitationMarkdown(text: string, sources?: string[]): string {
  return injectBulletPlainCitations(injectBracketCitations(text, sources), sources)
}
