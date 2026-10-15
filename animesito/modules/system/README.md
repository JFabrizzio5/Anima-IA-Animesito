# System

Owns what a login-less app bound to localhost still has to defend: the
`localguard` plugin refuses any `Host` outside the allow-list (DNS rebinding)
and any state-changing request without the `X-Animesito: 1` header (CSRF; a
cross-origin page cannot add it without a preflight the CORS allow-list
refuses). Health and docs endpoints are exempt.
