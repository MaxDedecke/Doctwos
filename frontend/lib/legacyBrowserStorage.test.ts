import { afterEach, describe, expect, it } from 'vitest';
import { LEGACY_BROWSER_STORAGE_SCRIPT } from './legacyBrowserStorage';

const run = () => new Function(LEGACY_BROWSER_STORAGE_SCRIPT)();

describe('LEGACY_BROWSER_STORAGE_SCRIPT', () => {
  afterEach(() => {
    localStorage.clear();
    document.cookie = 'codena-theme=; Max-Age=0; Path=/';
    document.cookie = 'doctus-theme=; Max-Age=0; Path=/';
  });

  it('copies doctus-* settings to codena-* without overwriting newer values', () => {
    localStorage.setItem('doctus-language', 'en');
    localStorage.setItem('doctus-active-profile-id', '7');
    localStorage.setItem('codena-active-profile-id', '9');
    localStorage.setItem('other-key', 'x');
    run();
    expect(localStorage.getItem('codena-language')).toBe('en');
    expect(localStorage.getItem('codena-active-profile-id')).toBe('9');
    expect(localStorage.getItem('codena-other-key')).toBeNull();
  });

  it('carries the theme cookie over once', () => {
    document.cookie = 'doctus-theme=light; Path=/';
    run();
    expect(document.cookie).toMatch(/codena-theme=light/);
  });

  it('keeps an existing codena-theme cookie', () => {
    document.cookie = 'doctus-theme=light; Path=/';
    document.cookie = 'codena-theme=dark; Path=/';
    run();
    expect(document.cookie).toMatch(/codena-theme=dark/);
  });
});
