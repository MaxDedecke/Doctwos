import { describe, expect, it } from 'vitest';

import { sanitizeSvg } from './sanitize';

describe('sanitizeSvg', () => {
  it('keeps Mermaid foreignObject labels while removing executable markup', () => {
    const clean = sanitizeSvg(
      '<svg><foreignObject><div xmlns="http://www.w3.org/1999/xhtml" onclick="evil()">Beschriftung</div></foreignObject><script>alert(1)</script></svg>'
    );

    expect(clean).toContain('foreignObject');
    expect(clean).toContain('Beschriftung');
    expect(clean).not.toContain('onclick');
    expect(clean).not.toContain('<script');
  });
});
