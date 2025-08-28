# FaxRetrieverAdmin (FRA) Architecture & Security Overview — v2.0

## 1. System Purpose

FaxRetrieverAdmin (FRA) functions as the central licensing authority, scoped token issuer, and retriever enforcement system for all FaxRetriever (FR) clients. It securely manages reseller credentials, issues per-domain JWTs, supplies SkySwitch bearer tokens, and enforces single-client retrieval integrity.

FRA operates with strict separation-of-duties: it never processes, stores, or interacts with fax content or job metadata, maintaining HIPAA-aligned isolation from client data.

---

## 2. Roles and Responsibilities

### FRA:
- Encrypts and stores reseller credentials (`reseller_blob`)
- Registers clients and assigns unique `domain_uuid` identifiers
- Generates and validates per-client `authentication_token`
- Issues JWTs via `/init`, scoped to domain and device
- Delivers bearer tokens via `/bearer` from encrypted domain-level cache
- Enforces single retriever assignment per fax number via `retriever_assignments` map
- Communicates retriever status via JWT field `retriever_status`
- Logs all access and changes to `access_logs` and `audit_logs`
- Performs proactive refreshes of bearer tokens within 1 hour of expiration.

### FaxRetriever (FR):
- Configures with `fax_user` and `authentication_token`
- Requests JWT via `/init`; requests bearer token via `/bearer`
- Performs all faxing operations using bearer token only
- Retains no reseller credentials or decrypted token data
- Enforces retriever lock on launch; obeys `retriever_status=denied`
- Stores client config at `%LOCALAPPDATA%\Clinic Networking, LLC\FaxRetriever\`

### Admin:
- Uses FRA GUI to manage resellers and client registrations
- Assigns `fax_user`, provisioned fax numbers, and issues `authentication_token`
- Views retriever status and token health per client
- Reassigns retriever and reissues tokens as needed

---

## 3. Authentication and Token Flow

1. **Reseller Registration (Admin):**
   - Fields: `reseller_id`, `voice_api_user`, `voice_api_password`, `msg_api_user`, `msg_api_password`, contact info
   - Stored as encrypted `reseller_blob` using AES-GCM keyed by `reseller_id`

2. **Client Registration (Admin):**
   - Fields: `fax_user`, `authentication_token`, `all_fax_numbers`, `retriever_assignments`: {"+1405...": "HOSTNAME"}
   - Internal: `domain_uuid` assigned on creation

3. **Client Initialization (FR):**
   - Inputs: `fax_user`, `authentication_token`
   - Sends POST `/init` to FRA
   - Output: `jwt_token`, `domain_uuid`, `retriever_status` (`allowed` or `denied`), `all_fax_numbers`: [list]

4. **Bearer Token Acquisition (FR):**
   - Sends POST `/bearer` with JWT
   - FRA validates JWT, returns bearer token + timestamps

5. **Token Usage (FR):**
   - Bearer token retained in memory
   - Used exclusively for SkySwitch API access

---

## 4. Token Specifications

### Authentication Token
- Format: `#####-#####`
- One-time use during install or manual reset
- Unique per `fax_user`

### JWT Access Token
- Signed with HS256
- Claims: `domain_uuid`, `device_id`, `retriever_status`, `iat`, `exp`
- TTL: 24 hours
- Stateless; validated via signature and expiration

### SkySwitch Bearer Token
- Retrieved per `fax_user` using reseller credentials
- Cached in encrypted storage
- TTL: ~24 hours (defined by SkySwitch)
- Proactively refreshed by FRA before expiration

---

## 5. Retriever Assignment Logic

- `retriever_assignments`[fax_number] enforced per selected number
- During `/init`:
  - If no retriever is assigned to the desired number and FR is in `sender_receiver` mode → assign retriever
  - If retriever exists and requesting device_id ≠ assigned → set `retriever_status=denied`
- FR disables retrieval functions if `retriever_status=denied`
- Reassignment is manual or admin-controlled
  - At the client-level, the configured receiver must disable retrieval before reassignment
  - At the FRA-level, the admin can reassign the retriever to a different device_id

---

## 6. API Endpoints

### `POST /init`
- Input: `fax_user`, `authentication_token`
- Output: `jwt_token`, `domain_uuid`, `retriever_status`, `all_fax_numbers`

### `POST /bearer`
- Header: `Authorization: Bearer <JWT>`
- Output: `bearer_token`, `bearer_token_retrieved`, `bearer_token_expires_at`

---

## 7. Credential and Configuration Storage

### Reseller Record (`resellers` collection):
- Encrypted fields: `reseller_id`, API credentials, contact metadata
- Operational metadata:
  - `bearer_token_last_issued`: timestamp of last SkySwitch token pull
  - `bearer_token_expires_at`: SkySwitch-declared expiration
  - `bearer_token_present`: boolean cache indicator

### Client Record (`clients` collection):
- Fields: `fax_user`, `authentication_token`, `domain_uuid`, `all_fax_numbers`, `retriever_assignments: { fax_number: hostname }`
- Indexed by `reseller_id`

---

## 8. Bearer Token Cache Model

- Tokens cached per `fax_user` in encrypted storage
- Includes `bearer_token`, `bearer_token_retrieved`, `bearer_token_expires_at`
- Auto-refresh occurs within one hour of expiry
- Ensures continuity with no client-side renewal logic

---

## 9. Logging and Auditing

### Collections:
- `access_logs` (90-day TTL): init/bearer usage, token flows
- `audit_logs` (365-day TTL): admin actions, config changes, errors

### Required Fields:
- `timestamp`, `event_type`, `domain_uuid`, `device_id`, `actor`, `object`, `note`

### UI Indicators:
- Green: payload present  
- Red: destructive action  
- Amber: failure or error  
- White: neutral event

---

## 10. Security Controls

- TLS enforced on all endpoints
- JWTs signed with HS256; rotation supported
- No SkySwitch or reseller credentials ever exposed to clients
- `authentication_token` has no runtime access power
- All bearer tokens are single-source (FRA) and encrypted at rest

---

## 11. Revocation and Recovery

- Clients can be set `active: false`; JWTs become invalid
- FRA blocks bearer issuance for inactive domains
- Admin may:
  - Reissue `authentication_token`
  - Reassign retriever via FRA GUI

---

## 12. Compliance Statement

FRA does not ingest, process, or store any fax transmissions, file attachments, or job metadata.

All credential handling is encrypted and access-scoped.  
All token issuance is controlled, scoped, and logged.  
All retriever assignment is explicit and singular per domain.

FRA is the sole SkySwitch bearer token authority for the FaxRetriever platform.