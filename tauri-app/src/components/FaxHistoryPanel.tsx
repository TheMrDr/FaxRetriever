import { useState, useEffect, useCallback } from "react";
import { invoke } from "../lib/sidecar";
import FaxCard from "./FaxCard";
import type { FaxCardProps } from "./FaxCard";

// Placeholder data for dev mode / initial render
const SAMPLE_FAXES: FaxCardProps[] = [
  {
    id: "1",
    direction: "inbound",
    number: "(555) 123-4567",
    date: "2026-03-07 10:30 AM",
    pages: 3,
    status: "Downloaded",
  },
  {
    id: "2",
    direction: "outbound",
    number: "(555) 234-5678",
    date: "2026-03-07 09:15 AM",
    pages: 1,
    status: "Delivered",
  },
  {
    id: "3",
    direction: "inbound",
    number: "(555) 345-6789",
    date: "2026-03-06 04:45 PM",
    pages: 5,
    status: "Not Downloaded",
  },
  {
    id: "4",
    direction: "outbound",
    number: "(555) 456-7890",
    date: "2026-03-06 02:20 PM",
    pages: 2,
    status: "Failed",
  },
  {
    id: "5",
    direction: "inbound",
    number: "(555) 567-8901",
    date: "2026-03-06 11:00 AM",
    pages: 1,
    status: "Downloaded",
  },
  {
    id: "6",
    direction: "inbound",
    number: "(555) 678-9012",
    date: "2026-03-05 03:15 PM",
    pages: 8,
    status: "Downloaded",
  },
  {
    id: "7",
    direction: "outbound",
    number: "(555) 789-0123",
    date: "2026-03-05 01:45 PM",
    pages: 4,
    status: "Delivered",
  },
];

type FilterDirection = "all" | "inbound" | "outbound";

export default function FaxHistoryPanel() {
  const [faxes, setFaxes] = useState<FaxCardProps[]>(SAMPLE_FAXES);
  const [filter, setFilter] = useState<FilterDirection>("all");
  const [loading, setLoading] = useState(false);

  const loadFaxes = useCallback(async () => {
    setLoading(true);
    try {
      const result = await invoke<{ faxes?: FaxCardProps[] }>("get_fax_history", {
        page: 1,
        direction: filter === "all" ? undefined : filter,
      });
      if (result?.faxes?.length) {
        setFaxes(result.faxes);
      }
    } catch {
      // Keep sample data on error
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    loadFaxes();
  }, [loadFaxes]);

  const filtered =
    filter === "all"
      ? faxes
      : faxes.filter((f) => f.direction === filter);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-5 pt-5 pb-3">
        <h2 className="text-base font-semibold text-text-primary">
          Fax History
        </h2>

        <div className="flex items-center gap-2">
          {/* Direction filter */}
          <div className="flex rounded-md border border-border overflow-hidden text-[11px]">
            {(["all", "inbound", "outbound"] as FilterDirection[]).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-2.5 py-1 transition-colors capitalize ${
                  filter === f
                    ? "bg-accent text-white"
                    : "bg-surface text-text-secondary hover:bg-background"
                }`}
              >
                {f === "all" ? "All" : f === "inbound" ? "In" : "Out"}
              </button>
            ))}
          </div>

          <button
            onClick={loadFaxes}
            disabled={loading}
            className="text-xs text-accent hover:text-accent-hover transition-colors disabled:opacity-50"
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>
      </div>

      {/* Fax list */}
      <div className="flex-1 overflow-y-auto px-5 pb-5">
        <div className="space-y-2">
          {filtered.map((fax) => (
            <FaxCard key={fax.id} {...fax} />
          ))}
        </div>

        {filtered.length === 0 && (
          <div className="text-center py-12">
            <p className="text-sm text-text-muted">No faxes found</p>
          </div>
        )}

        {filtered.length > 0 && (
          <div className="text-center py-4">
            <button className="text-xs text-accent hover:text-accent-hover transition-colors">
              Load older faxes
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
