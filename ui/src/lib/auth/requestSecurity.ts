import type { NextRequest } from 'next/server';

export function isSecureRequest(request: NextRequest): boolean {
  const forwardedProto = request.headers
    .get('x-forwarded-proto')
    ?.split(',')[0]
    ?.trim()
    .toLowerCase();

  return request.nextUrl.protocol === 'https:' || forwardedProto === 'https';
}
