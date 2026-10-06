import { describe, expect, it } from 'vitest';
import { deploymentSlug } from './LocalDeploymentForm';

describe('deploymentSlug', () => {
  it('derives a container-safe name from the profile name', () => {
    expect(deploymentSlug('Qwen Coder 14B (lokal)', 'x', [])).toBe('qwen-coder-14b-lokal');
    expect(deploymentSlug('Größe & Übung', 'x', [])).toBe('grosse-ubung');
  });

  it('falls back when the name has no usable characters or is too short', () => {
    expect(deploymentSlug('!!!', 'llamacpp-chat', [])).toBe('llamacpp-chat');
    expect(deploymentSlug('a', 'x', [])).toBe('a-x');
  });

  it('keeps names unique and within the length limit', () => {
    expect(deploymentSlug('Test', 'x', ['test', 'test-2'])).toBe('test-3');
    expect(deploymentSlug('a'.repeat(60), 'x', []).length).toBeLessThanOrEqual(26);
  });
});
