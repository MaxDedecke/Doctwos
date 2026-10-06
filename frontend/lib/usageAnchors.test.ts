import { describe, expect, it } from 'vitest';
import { computeUsageAnchor, type UsageReference } from './usageAnchors';

const run = (lines: string[], ref: Partial<UsageReference> & { type: string; dst_name: string; line: number; target: { name: string } }) => {
  const anchor = computeUsageAnchor({ edge_id: 1, ...ref } as UsageReference, (n) => lines[n - 1] ?? '', lines.length);
  return anchor ? lines[anchor.line - 1].slice(anchor.startColumn - 1, anchor.endColumn - 1) : null;
};

describe('computeUsageAnchor', () => {
  it('anchors a Java call on the method name, without arguments', () => {
    const line = '    client.getConfiguration().toMetadataGenerator(x);';
    expect(run([line], { type: 'CALLS', dst_name: 'client.getConfiguration().toMetadataGenerator', line: 1,
      start_column: line.indexOf('toMetadataGenerator'), end_column: line.indexOf('toMetadataGenerator') + 21, target: { name: 'toMetadataGenerator' } })).toBe('toMetadataGenerator');
  });

  it('anchors type usage, instantiation and extends on the type name', () => {
    const line = '  Foo x = new SAML2Client(cfg());';
    const start = line.indexOf('SAML2Client');
    expect(run([line], { type: 'INSTANTIATES', dst_name: 'SAML2Client', line: 1, start_column: start, end_column: line.length - 1, target: { name: 'SAML2Client' } })).toBe('SAML2Client');
    const ext = 'public class A extends BaseTest {';
    const s2 = ext.indexOf('BaseTest');
    expect(run([ext], { type: 'EXTENDS', dst_name: 'BaseTest', line: 1, start_column: s2, end_column: s2 + 8, target: { name: 'BaseTest' } })).toBe('BaseTest');
  });

  it('anchors an import on the qualified name, and a qualified type on the segment naming the target', () => {
    const imp = 'import static org.x.Y.CONST;';
    expect(run([imp], { type: 'IMPORTS', dst_name: 'org.x.Y.CONST', line: 1, start_column: 0, end_column: imp.length, target: { name: 'CONST' } })).toBe('CONST');
    const q = '  Map.Entry e;';
    expect(run([q], { type: 'USES_TYPE', dst_name: 'Map.Entry', line: 1, start_column: 2, end_column: 11, target: { name: 'Map' } })).toBe('Map');
  });

  it('finds COBOL targets by name within the statement lines', () => {
    const lines = ["           CALL 'CBLTDLI' USING X", '           MOVE A TO WS-TOTAL'];
    expect(run(lines, { type: 'CALL', dst_name: 'CBLTDLI', line: 1, end_line: 1, target: { name: 'CBLTDLI' } })).toBe('CBLTDLI');
    expect(run(lines, { type: 'WRITES', dst_name: 'WS-TOTAL', line: 2, end_line: 2, target: { name: 'WS-TOTAL' } })).toBe('WS-TOTAL');
  });

  it('falls back to the name search when the columns do not fit', () => {
    expect(run(['  call(foo);'], { type: 'CALLS', dst_name: 'foo', line: 1, start_column: 90, end_column: 95, target: { name: 'foo' } })).toBe('foo');
    expect(run(['x'], { type: 'CALLS', dst_name: 'nope', line: 1, target: { name: 'nope' } })).toBeNull();
  });
});
