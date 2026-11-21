import { NextResponse, type NextRequest } from "next/server";

/** Must match `SESSION_COOKIE` in apps/api/src/altri_api/auth/service.py. */
export const SESSION_COOKIE = "altri_session";

/**
 * Optimistic check only: no cookie means no session, so skip straight to sign-in instead of rendering a page
 * that would 401. Whether the cookie is valid, and what the user may see, is decided by the API on every call.
 */
export function proxy(request: NextRequest) {
  if (!request.cookies.has(SESSION_COOKIE)) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Everything except sign-in, the proxied API, and static assets.
  matcher: ["/((?!login|api/|_next/|favicon.ico).*)"],
};
