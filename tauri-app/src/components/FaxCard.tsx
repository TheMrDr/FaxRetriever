import { useState, useEffect } from "react";
import { invoke } from "../lib/sidecar";

export interface FaxCardProps {
  id: string;
  direction: "inbound" | "outbound";
  number: string;
  date: string;
  pages: number;
  status: string;
  thumbnailUrl?: string;
  /** Integration source: "crx", "lrx", or undefined for manual/unknown */
  source?: string;
}

function statusColor(status: string): string {
  switch (status.toLowerCase()) {
    case "downloaded":
    case "delivered":
      return "text-success";
    case "not downloaded":
    case "not_downloaded":
    case "failed":
      return "text-error";
    case "pending":
    case "unavailable":
      return "text-warning";
    default:
      return "text-text-secondary";
  }
}

function statusBg(status: string): string {
  switch (status.toLowerCase()) {
    case "downloaded":
    case "delivered":
      return "bg-success/10";
    case "not downloaded":
    case "not_downloaded":
    case "failed":
      return "bg-error/10";
    case "pending":
    case "unavailable":
      return "bg-warning/10";
    default:
      return "bg-text-secondary/10";
  }
}

function statusLabel(status: string): string {
  switch (status.toLowerCase()) {
    case "downloaded":
      return "Downloaded";
    case "delivered":
      return "Delivered";
    case "not downloaded":
    case "not_downloaded":
      return "Not Downloaded";
    case "failed":
      return "Failed";
    case "pending":
      return "Pending";
    case "unavailable":
      return "Unavailable";
    default:
      return status;
  }
}

function PlaceholderThumb({ pages }: { pages: number }) {
  return (
    <div className="w-[72px] h-[96px] bg-background rounded border border-border flex flex-col items-center justify-center shrink-0">
      <svg
        width="24"
        height="28"
        viewBox="0 0 24 28"
        fill="none"
        className="text-text-muted opacity-40"
      >
        <rect
          x="1"
          y="1"
          width="22"
          height="26"
          rx="2"
          stroke="currentColor"
          strokeWidth="1.5"
        />
        <line x1="5" y1="7" x2="19" y2="7" stroke="currentColor" strokeWidth="1" />
        <line x1="5" y1="11" x2="19" y2="11" stroke="currentColor" strokeWidth="1" />
        <line x1="5" y1="15" x2="15" y2="15" stroke="currentColor" strokeWidth="1" />
        <line x1="5" y1="19" x2="17" y2="19" stroke="currentColor" strokeWidth="1" />
      </svg>
      <span className="text-[9px] text-text-muted mt-1">
        {pages}p
      </span>
    </div>
  );
}

const SOURCE_BADGE: Record<string, { label: string; color: string; bg: string; title: string }> = {
  crx: {
    label: "CRx",
    color: "text-blue-700 dark:text-blue-300",
    bg: "bg-blue-100 dark:bg-blue-900/40",
    title: "Auto-sent by Computer-Rx integration",
  },
  lrx: {
    label: "LRx",
    color: "text-purple-700 dark:text-purple-300",
    bg: "bg-purple-100 dark:bg-purple-900/40",
    title: "Auto-sent by Liberty Rx integration",
  },
};

export default function FaxCard({
  id,
  direction,
  number,
  date,
  pages,
  status,
  thumbnailUrl: initialThumbnail,
  source,
}: FaxCardProps) {
  const [thumbnail, setThumbnail] = useState<string | null>(
    initialThumbnail || null
  );
  const [thumbError, setThumbError] = useState(false);

  useEffect(() => {
    if (thumbnail || thumbError) return;
    invoke<{ thumbnail?: string }>("get_fax_thumbnail", { fax_id: id })
      .then((result) => {
        if (result?.thumbnail) {
          setThumbnail(result.thumbnail);
        } else {
          setThumbError(true);
        }
      })
      .catch(() => setThumbError(true));
  }, [id, thumbnail, thumbError]);

  const bgClass =
    direction === "inbound" ? "bg-inbound-bg" : "bg-outbound-bg";
  const dirLabel = direction === "inbound" ? "IN" : "OUT";
  const dirColor =
    direction === "inbound"
      ? "bg-accent text-white"
      : "bg-primary text-text-on-primary";
  const dirDesc = direction === "inbound" ? "From" : "To";

  return (
    <div
      className={`${bgClass} rounded-lg border border-border p-3 hover:shadow-md transition-shadow cursor-pointer group`}
    >
      <div className="flex gap-3">
        {/* Thumbnail */}
        <div className="relative">
          {thumbnail ? (
            <img
              src={
                thumbnail.startsWith("data:")
                  ? thumbnail
                  : `data:image/jpeg;base64,${thumbnail}`
              }
              alt={`Fax ${dirDesc.toLowerCase()} ${number}`}
              className="w-[72px] h-[96px] object-cover rounded border border-border shrink-0"
            />
          ) : (
            <PlaceholderThumb pages={pages} />
          )}
          {/* Direction badge overlaid on thumbnail */}
          <span
            className={`${dirColor} absolute -top-1.5 -left-1.5 text-[9px] font-bold px-1.5 py-0.5 rounded shadow-sm`}
          >
            {dirLabel}
          </span>
        </div>

        {/* Details */}
        <div className="flex-1 min-w-0 flex flex-col justify-between py-0.5">
          <div>
            <p className="text-[11px] text-text-muted uppercase tracking-wide">
              {dirDesc}
            </p>
            <p className="text-sm font-semibold text-text-primary truncate mt-0.5">
              {number}
            </p>
            <p className="text-xs text-text-muted mt-1">{date}</p>
          </div>

          <div className="flex items-center justify-between mt-2">
            <div className="flex items-center gap-1.5">
              <span
                className={`${statusColor(status)} ${statusBg(status)} text-[11px] font-medium px-2 py-0.5 rounded-full`}
              >
                {statusLabel(status)}
              </span>
              {source && SOURCE_BADGE[source] && (
                <span
                  className={`${SOURCE_BADGE[source].color} ${SOURCE_BADGE[source].bg} text-[10px] font-semibold px-1.5 py-0.5 rounded`}
                  title={SOURCE_BADGE[source].title}
                >
                  {SOURCE_BADGE[source].label}
                </span>
              )}
            </div>
            <span className="text-xs text-text-muted">
              {pages} {pages === 1 ? "page" : "pages"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
