import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';

import { isSecureRequest } from '@/lib/auth/requestSecurity';

const OSS_TOKEN_COOKIE = 'dograh_auth_token';
const OSS_USER_COOKIE = 'dograh_auth_user';

export async function POST(request: NextRequest) {
  const cookieStore = await cookies();
  const secure = isSecureRequest(request);

  cookieStore.set(OSS_TOKEN_COOKIE, '', {
    httpOnly: true,
    secure,
    sameSite: 'lax',
    maxAge: 0,
    path: '/',
  });

  cookieStore.set(OSS_USER_COOKIE, '', {
    httpOnly: true,
    secure,
    sameSite: 'lax',
    maxAge: 0,
    path: '/',
  });

  return NextResponse.json({ success: true });
}
