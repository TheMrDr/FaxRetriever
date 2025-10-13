# FaxRetrieverAdmin (FRA) — Interaction Overview (LibertyRx additions)

Version: 2.2

This document summarizes the LibertyRx-related endpoints and scopes added to FRA for the FaxRetriever desktop clients and the FRA Admin GUI.

---

## Device endpoint (client-side)

GET /integrations/libertyrx/vendor_basic.get
- Purpose: Return the precomputed Liberty vendor Basic header value (base64) for the authenticated device’s reseller.
- Auth: Authorization: Bearer <JWT>
- Required scope: liberty:basic.read
- Success 200 response body:
  {
    "basic_b64": "dmVuZG9yOnBhc3M=",
    "rotated_at": "2025-10-12T01:49:00Z"
  }
- Error responses:
  - 401 Unauthorized: missing/invalid JWT or missing scope
  - 404 Not Found: reseller record has no saved Liberty vendor basic value

Notes
- The endpoint never returns raw vendor username/password.
- The value is stored by the Admin via the routes below and is intended to be cached on the device encrypted at rest (DPAPI).

---

## Admin GUI endpoints (per reseller)

Base path: /admin/integrations/liberty/{reseller_id}/basic

- GET …/basic
  - Purpose: Read the saved Liberty vendor Basic header for the given reseller.
  - Auth: X-Admin-Key header must match environment variable ADMIN_API_KEY (dev mode: open if ADMIN_API_KEY unset).
  - Success 200 response: { "basic_b64": "…", "rotated_at": "…" }
  - 404 if not configured.

- POST …/basic
  - Purpose: Save or rotate the vendor Basic header value for the reseller.
  - Auth: X-Admin-Key required as above.
  - Request JSON: either
    { "basic_b64": "..." }
    or
    { "username": "vendor-user", "password": "secret" }  // server computes base64(username:password)
  - Success 200 response: { "success": true, "basic_b64": "…", "rotated_at": "…" }
  - 400 if neither basic_b64 nor username/password provided; 500 on persistence failure.

- DELETE …/basic
  - Purpose: Clear the saved value (and optional encrypted vendor creds).
  - Auth: X-Admin-Key required as above.
  - Success 200 response: { "success": true }

Notes
- The server stores only the precomputed base64 value and a rotation timestamp. Optionally, encrypted raw creds may be kept for convenience but are never returned to devices.

---

## Security & scopes (recap)

- JWT claims (device): iss, aud, sub (domain_uuid), device_id, scope (list of strings), iat, nbf, exp.
- Scope required for device endpoint: liberty:basic.read.
- Admin GUI endpoints use X-Admin-Key protection only; they are not exposed for public device use.

---

## Client-side use (FaxRetriever)

- After a successful /bearer call, the desktop app calls GET /integrations/libertyrx/vendor_basic.get with its JWT.
- If a new basic_b64 is returned (different from stored), the app updates its encrypted global config and clears any Liberty 401 retry gate in the local queue.

---

## Error handling guidance

- 401 from device endpoint: client should retry after obtaining a fresh JWT or when scopes are corrected.
- 404 from device endpoint: indicates admin-side configuration not yet completed for that reseller.

---

## Related

- Receiver flow forwards inbound faxes directly to LibertyRx using the stored vendor Basic and per-pharmacy Customer header. See Docs/“FaxRetriever 2.0 and FaxRetrieverAdmin 2.0 - System Alignment Reference.md” LibertyRx section.
