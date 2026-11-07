import { describe, expect, it } from 'vitest';
import { formFromProfile, profileFromForm } from './buildProfileForm';

describe('build profile form', () => {
  const stored = {
    source: {
      compiler_family: 'ibm-enterprise-cobol',
      encoding: 'CCSID-1141',
      defines: { ENV: 'PROD' },
      copy_search_order: ['copy/team', 'copy/common'],
      source_columns: { code_end: 72 },
    },
    paths: { 'legacy/os-vs': { source_format: 'fixed' } },
  };

  it('round-trips a stored profile and keeps fields the form does not show', () => {
    const form = formFromProfile({ build_profile: stored, language_paths: { 'MEMBERS/COB': 'cobol' } });

    expect(form.defines).toBe('ENV=PROD');
    expect(form.copy_search_order).toBe('copy/team\ncopy/common');
    expect(form.language_paths).toBe('MEMBERS/COB = cobol');

    const result = profileFromForm({ ...form, debug_mode: true }, stored);
    expect(result).toEqual({
      body: {
        build_profile: {
          source: { ...stored.source, debug_mode: true },
          paths: stored.paths,
        },
        language_paths: { 'MEMBERS/COB': 'cobol' },
      },
    });
  });

  it('reads an old flat profile as the source-wide part', () => {
    expect(formFromProfile({ build_profile: { source_format: 'free' }, language_paths: null }).source_format).toBe('free');
  });

  it('removes the profile when the form is empty', () => {
    const empty = formFromProfile({ build_profile: null, language_paths: null });
    expect(profileFromForm(empty, null)).toEqual({ body: { build_profile: null, language_paths: null } });
  });

  it('names the field of a line it cannot read', () => {
    const form = formFromProfile({ build_profile: null, language_paths: null });
    expect(profileFromForm({ ...form, defines: 'ENV' }, null)).toEqual({ error: { field: 'defines', line: 'ENV' } });
    expect(profileFromForm({ ...form, language_paths: 'MEMBERS' }, null)).toEqual({ error: { field: 'language_paths', line: 'MEMBERS' } });
    expect(profileFromForm({ ...form, paths_json: '[1]' }, null)).toEqual({ error: { field: 'paths_json' } });
  });
});
