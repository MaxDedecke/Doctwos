import { describe, expect, it } from 'vitest';
import { computeEntityAnchor, pickFileLevelEntity } from './entityAnchors';

const reader = (lines: string[]) => (n: number) => lines[n - 1] ?? '';
const anchor = (lines: string[], ent: Parameters<typeof computeEntityAnchor>[0]) =>
  computeEntityAnchor(ent, reader(lines), lines.length);

describe('computeEntityAnchor', () => {
  it('finds the method name below annotations instead of the annotation line', () => {
    const lines = ['  @Override', '  @Transactional(readOnly = true,', '      timeout = 3)', '  public void onSubmit() {', '  }'];
    expect(anchor(lines, { name: 'onSubmit', type: 'method', start_line: 1, end_line: 5 }))
      .toEqual({ line: 4, startColumn: 15, endColumn: 23 });
  });

  it('does not match the name inside the annotation text', () => {
    const lines = ['@Configuration("AMConsoleContext")', 'public class AMConsoleContext {'];
    const result = anchor(lines, { name: 'AMConsoleContext', type: 'class', start_line: 1, end_line: 2 });
    expect(result?.line).toBe(2);
  });

  it('keeps the start line when the name is already there', () => {
    expect(anchor(['  private int count;'], { name: 'count', type: 'field', start_line: 1, end_line: 1 }))
      .toEqual({ line: 1, startColumn: 15, endColumn: 20 });
  });

  it('anchors lambdas on their arrow and anonymous classes on their brace', () => {
    const lambdaLine = ['        clientApp.getProperties().removeIf(p -> modelObject.test(p));'];
    const lambda = anchor(lambdaLine, { name: '<lambda@1:43>', type: 'lambda', start_line: 1 });
    expect(lambdaLine[0].slice(lambda!.startColumn - 1, lambda!.endColumn - 1)).toBe('->');
    const anonLine = ['        AjaxButton search = new AjaxButton("search") {'];
    const anon = anchor(anonLine, { name: '<anonymous@1:53>', type: 'anonymous_class', start_line: 1 });
    expect(anonLine[0].slice(anon!.startColumn - 1, anon!.endColumn - 1)).toBe('{');
  });

  it('anchors static initializers, EXEC blocks, SQL blocks and HTML forms on their keyword', () => {
    expect(anchor(['    static {'], { name: '<clinit>', type: 'initializer', start_line: 1 })).toEqual({ line: 1, startColumn: 5, endColumn: 11 });
    const exec = anchor(['            EXEC DLI GN USING PCB(X)'], { name: 'EXEC-DLI-BLOCK@1', type: 'exec_block', start_line: 1 });
    expect(exec?.startColumn).toBe(13);
    expect(anchor(['       EXEC SQL'], { name: 'SQL-BLOCK@1', type: 'sql_block', start_line: 1 })?.endColumn).toBe(16);
    expect(anchor(['  <form wicket:id="login">'], { name: '<current-page>', type: 'html_form', start_line: 1 })?.startColumn).toBe(3);
  });

  it('finds COBOL names in following lines (program id, EXEC resources, DD datasets)', () => {
    const program = ['       IDENTIFICATION DIVISION.', '       PROGRAM-ID. DBUNLDGS.'];
    expect(anchor(program, { name: 'DBUNLDGS', type: 'program', start_line: 1, end_line: 300 })?.line).toBe(2);
    const exec = ['EXEC DLI GN USING PCB(PAUT-PCB-NUM)', '     SEGMENT (PAUTSUM0)'];
    expect(anchor(exec, { name: 'PAUTSUM0', type: 'exec_resource', start_line: 1, end_line: 2 })?.line).toBe(2);
    const dd = ['//TRANVSAM DD DISP=SHR,', '//   DSN=AWS.M2.CARDDEMO.TRANSACT.VSAM.KSDS'];
    expect(anchor(dd, { name: 'AWS.M2.CARDDEMO.TRANSACT.VSAM.KSDS', type: 'jcl_dataset', start_line: 1, end_line: 2 })?.line).toBe(2);
  });

  it('uses the artifactId for Maven objects', () => {
    const pom = ['    <dependency>', '      <groupId>org.x</groupId>', '      <artifactId>syncope-common-idm-lib</artifactId>'];
    expect(anchor(pom, { name: 'org.x:syncope-common-idm-lib', type: 'maven_dependency', start_line: 1, end_line: 1 })?.line).toBe(3);
  });

  it('returns null for file-level objects and unresolvable names', () => {
    expect(anchor(['/* license */'], { name: 'Foo.java', type: 'compilation_unit', start_line: 1 })).toBeNull();
    expect(anchor(['x'], { name: 'Nope', type: 'method', start_line: 1, end_line: 1 })).toBeNull();
  });
});

describe('pickFileLevelEntity', () => {
  it('prefers the compilation unit / copybook / JCL file of a file', () => {
    const picked = pickFileLevelEntity([{ name: 'a', type: 'method' }, { name: 'B', type: 'copybook' }, { name: 'p', type: 'maven_source_root' }]);
    expect(picked?.name).toBe('B');
    expect(pickFileLevelEntity([{ name: 'a', type: 'method' }])).toBeNull();
  });
});
