/**
 * React hooks for sidecar IPC.
 * Provides invoke() and event subscription with automatic cleanup.
 */

import { useEffect, useCallback, useRef, useState } from "react";
import {
  startSidecar,
  stopSidecar,
  invoke as sidecarInvoke,
  onEvent,
  isSidecarRunning,
  isDevMode,
  tauriInvoke,
} from "../lib/sidecar";

/**
 * Hook to manage sidecar lifecycle.
 * Call this once at the app root.
 */
export function useSidecarLifecycle() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [devMode, setDevMode] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    setDevMode(isDevMode());

    startSidecar()
      .then(async () => {
        if (isDevMode()) {
          setReady(true);
          return;
        }
        // Listen for the ready event from the real sidecar
        const unsub = onEvent("sidecar_ready", () => {
          setReady(true);
          unsub();
        });
        // Fallback: if sidecar_ready doesn't fire within 5s, consider it ready
        setTimeout(() => setReady(true), 5000);

        // Sync close-to-tray setting from sidecar config → Tauri window manager
        try {
          const settings = await sidecarInvoke<{ close_to_tray?: boolean }>("get_settings");
          if (settings?.close_to_tray) {
            tauriInvoke("set_close_to_tray", { enabled: true });
          }
        } catch {
          // Non-critical — default is false
        }
      })
      .catch((err) => {
        console.error("Failed to start sidecar:", err);
        setError(String(err));
        setReady(true);
      });

    return () => {
      stopSidecar();
    };
  }, []);

  return { ready, error, running: isSidecarRunning(), devMode };
}

/**
 * Hook to invoke a sidecar method.
 * Returns { invoke, loading, error, data }.
 */
export function useSidecarInvoke<T = unknown>() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<T | null>(null);

  const invoke = useCallback(
    async (method: string, params: Record<string, unknown> = {}) => {
      setLoading(true);
      setError(null);
      try {
        const result = await sidecarInvoke<T>(method, params);
        setData(result);
        return result;
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return { invoke, loading, error, data };
}

/**
 * Hook to subscribe to sidecar events with automatic cleanup.
 */
export function useSidecarEvent(
  event: string,
  handler: (data: unknown) => void
) {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    const unsub = onEvent(event, (data) => handlerRef.current(data));
    return unsub;
  }, [event]);
}
