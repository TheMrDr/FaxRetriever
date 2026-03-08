/**
 * FaxRetriever Sidecar IPC
 *
 * Manages the Python sidecar process and provides a typed JSON-RPC interface.
 * Frontend → Sidecar: JSON-RPC requests via stdin
 * Sidecar → Frontend: JSON events + RPC responses via stdout
 *
 * In browser-only dev mode (no Tauri runtime), uses mock responses with real data.
 */

import {
  MOCK_FAX_HISTORY,
  MOCK_CALLER_IDS,
  MOCK_CONTACTS,
  getMockThumbnail,
} from "../dev/mockData";

type RpcCallback = {
  resolve: (value: unknown) => void;
  reject: (reason: unknown) => void;
};

type EventHandler = (data: unknown) => void;

// Detect if Tauri runtime is available
const IS_TAURI =
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

/**
 * Call a Tauri Rust command (not a sidecar command).
 * No-op in browser dev mode.
 */
export async function tauriInvoke<T = unknown>(
  cmd: string,
  args: Record<string, unknown> = {}
): Promise<T | null> {
  if (!IS_TAURI) return null;
  const { invoke: tauriCmd } = await import("@tauri-apps/api/core");
  return tauriCmd<T>(cmd, args);
}

// ─── Mock mode (browser dev) ────────────────────────────────────────

function getMockResponse(
  method: string,
  params: Record<string, unknown>
): unknown {
  switch (method) {
    case "ping":
      return { pong: true };
    case "get_version":
      return { version: "3.0.0-dev" };
    case "get_app_info":
      return { version: "3.0.0-dev", platform: "browser-dev" };
    case "get_app_state":
      return {
        ready: true,
        fax_user: "101@clinicnetworkingllc.23613.service",
        retriever_mode: "full",
        validation_status: true,
        has_bearer_token: true,
        bearer_token_expires: "2026-03-08T19:20:18",
        selected_fax_numbers: MOCK_CALLER_IDS,
        all_fax_numbers: MOCK_CALLER_IDS,
        save_path: "C:\\Faxes",
      };
    case "get_settings":
      return {
        fax_user: "101@clinicnetworkingllc.23613.service",
        polling_frequency: 5,
        download_method: "PDF",
        file_name_format: "cid",
        save_path: "C:\\Faxes",
        print_faxes: false,
        printer_name: "",
        notifications_enabled: true,
        close_to_tray: false,
        theme: "dark",
        logging_level: "Debug",
        integration_enabled: false,
        integration_software: "",
        libertyrx_enabled: false,
        libertyrx_port: 18761,
      };
    case "get_fax_history":
      return MOCK_FAX_HISTORY;
    case "get_fax_thumbnail": {
      const faxId = String(params.fax_id || "");
      const thumb = getMockThumbnail(faxId);
      return { thumbnail: thumb };
    }
    case "get_contacts":
      return { contacts: MOCK_CONTACTS };
    case "list_scanners":
      return { scanners: ["Mock Scanner WIA"] };
    case "get_outbox_jobs":
      return {
        jobs: [
          {
            key: "manual:abc123",
            type: "manual",
            dest: "14055551234",
            caller: "14058038006",
            file: "C:\\Faxes\\prescription_form.pdf",
            status: "accepted",
            attempts: 1,
            created_at: "2026-03-08T02:15:00Z",
            accepted_at: "2026-03-08T02:15:05Z",
            last_error: null,
          },
          {
            key: "crx:4401:fa92e",
            type: "crx",
            dest: "19135551000",
            caller: "14058038006",
            file: "C:\\Faxes\\refill_request_4401.pdf",
            status: "queued",
            attempts: 0,
            created_at: "2026-03-08T02:20:00Z",
            accepted_at: null,
            last_error: null,
          },
          {
            key: "crx:4388:b1c3d",
            type: "crx",
            dest: "14053648900",
            caller: "14058038006",
            file: "C:\\Faxes\\prior_auth_4388.pdf",
            status: "failed_delivery",
            attempts: 3,
            created_at: "2026-03-07T18:30:00Z",
            accepted_at: "2026-03-07T18:30:12Z",
            last_error: "Remote fax machine did not answer",
            next_eligible: null,
          },
          {
            key: "crx:4350:e7f8a",
            type: "crx",
            dest: "19280000000",
            caller: "14058038006",
            file: "C:\\Faxes\\verification_4350.pdf",
            status: "invalid_number",
            attempts: 0,
            created_at: "2026-03-07T14:00:00Z",
            accepted_at: null,
            last_error: "Invalid/ambiguous number: 928-000-0000",
          },
        ],
      };
    default:
      return { ok: true };
  }
}

// ─── Real sidecar (Tauri mode) ─────────────────────────────────────

let sidecarChild: import("@tauri-apps/plugin-shell").Child | null = null;
let nextId = 1;
const pendingCalls = new Map<number, RpcCallback>();
const eventHandlers = new Map<string, Set<EventHandler>>();
let lineBuffer = "";

function handleStdoutLine(line: string) {
  const trimmed = line.trim();
  if (!trimmed) return;

  try {
    const msg = JSON.parse(trimmed);

    if (msg.event) {
      const handlers = eventHandlers.get(msg.event);
      if (handlers) {
        for (const handler of handlers) {
          try {
            handler(msg.data);
          } catch (e) {
            console.error(`Event handler error for ${msg.event}:`, e);
          }
        }
      }
    } else if (msg.id !== undefined) {
      const pending = pendingCalls.get(msg.id);
      if (pending) {
        pendingCalls.delete(msg.id);
        if (msg.error) {
          pending.reject(new Error(msg.error));
        } else {
          pending.resolve(msg.result);
        }
      }
    }
  } catch {
    console.log("[sidecar stdout]", trimmed);
  }
}

function handleStdoutData(data: string) {
  lineBuffer += data;
  const lines = lineBuffer.split("\n");
  lineBuffer = lines.pop() || "";
  for (const line of lines) {
    handleStdoutLine(line);
  }
}

/**
 * Start the Python sidecar process.
 * In browser-only dev mode, this is a no-op.
 */
export async function startSidecar(): Promise<void> {
  if (!IS_TAURI) {
    console.log("[sidecar] Running in browser dev mode — using real mock data");
    return;
  }

  if (sidecarChild) {
    console.warn("Sidecar already running");
    return;
  }

  const { Command } = await import("@tauri-apps/plugin-shell");
  const sidecarCommand = Command.sidecar("binaries/fax-sidecar");

  sidecarCommand.stdout.on("data", handleStdoutData);

  sidecarCommand.stderr.on("data", (data: string) => {
    console.warn("[sidecar stderr]", data);
  });

  sidecarCommand.on("error", (error: string) => {
    console.error("[sidecar error]", error);
    sidecarChild = null;
    for (const [id, cb] of pendingCalls) {
      cb.reject(new Error("Sidecar process terminated"));
      pendingCalls.delete(id);
    }
  });

  sidecarCommand.on("close", (data) => {
    console.log("[sidecar closed] exit code:", data.code);
    sidecarChild = null;
  });

  sidecarChild = await sidecarCommand.spawn();
}

/**
 * Stop the sidecar process.
 */
export async function stopSidecar(): Promise<void> {
  if (sidecarChild) {
    await sidecarChild.kill();
    sidecarChild = null;
  }
}

/**
 * Send a JSON-RPC command to the sidecar and wait for the response.
 * In dev mode, returns mock data.
 */
export function invoke<T = unknown>(
  method: string,
  params: Record<string, unknown> = {}
): Promise<T> {
  if (!IS_TAURI) {
    return new Promise((resolve) => {
      setTimeout(() => {
        const mock = getMockResponse(method, params);
        console.log(`[sidecar mock] ${method} →`, mock);
        resolve(mock as T);
      }, 100);
    });
  }

  return new Promise((resolve, reject) => {
    if (!sidecarChild) {
      reject(new Error("Sidecar not running"));
      return;
    }

    const id = nextId++;
    pendingCalls.set(id, {
      resolve: resolve as (value: unknown) => void,
      reject,
    });

    const message = JSON.stringify({ id, method, params }) + "\n";
    sidecarChild.write(message).catch((err: unknown) => {
      pendingCalls.delete(id);
      reject(err);
    });

    setTimeout(() => {
      if (pendingCalls.has(id)) {
        pendingCalls.delete(id);
        reject(new Error(`RPC timeout: ${method}`));
      }
    }, 30000);
  });
}

/**
 * Subscribe to events pushed by the sidecar.
 */
export function onEvent(event: string, handler: EventHandler): () => void {
  if (!eventHandlers.has(event)) {
    eventHandlers.set(event, new Set());
  }
  eventHandlers.get(event)!.add(handler);

  return () => {
    eventHandlers.get(event)?.delete(handler);
  };
}

/**
 * Check if the sidecar is currently running (or mock mode is active).
 */
export function isSidecarRunning(): boolean {
  return !IS_TAURI || sidecarChild !== null;
}

/**
 * Whether we're running in dev mode (browser without Tauri).
 */
export function isDevMode(): boolean {
  return !IS_TAURI;
}
