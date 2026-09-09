// @vitest-environment node
import { NextRequest } from 'next/server';
import { describe, expect, it } from 'vitest';

import { isSecureRequest } from './requestSecurity';

describe('isSecureRequest', () => {
  it('keeps cookies usable for a production build served over private HTTP', () => {
    const request = new NextRequest('http://100.112.215.55:8091/api/auth/session');

    expect(isSecureRequest(request)).toBe(false);
  });

  it('marks cookies secure for direct HTTPS requests', () => {
    const request = new NextRequest('https://dograh.example/api/auth/session');

    expect(isSecureRequest(request)).toBe(true);
  });

  it('honors HTTPS terminated by a trusted reverse proxy', () => {
    const request = new NextRequest('http://ui:3010/api/auth/session', {
      headers: { 'x-forwarded-proto': 'HTTPS, http' },
    });

    expect(isSecureRequest(request)).toBe(true);
  });
});
