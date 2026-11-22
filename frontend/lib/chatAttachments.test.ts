import { describe, expect, it } from 'vitest';
import { readAttachments } from './chatAttachments';

describe('chat attachments', () => {
  it('accepts text files and rejects binary, empty and surplus ones', async () => {
    const files = [
      new File(['IEF450I ABEND=S0C7'], 'job.log'),
      new File(['\u0000\u0001'], 'bild.png'),
      new File(['   '], 'leer.txt'),
      new File(['MOVE 1 TO X.'], 'a.cbl'),
    ];
    const { accepted, rejected } = await readAttachments(files, 4);
    expect(accepted).toEqual([{ name: 'job.log', content: 'IEF450I ABEND=S0C7' }]);
    expect(rejected).toEqual(['bild.png', 'leer.txt', 'a.cbl']);
  });
});
