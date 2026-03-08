import { useState, useEffect, useRef } from "react";
import { invoke } from "../lib/sidecar";

interface Contact {
  id: string;
  name: string;
  fax: string;
}

interface Attachment {
  name: string;
  size: number;
}

function formatPhone(raw: string): string {
  // Strip +1 or 1 prefix and non-digit chars
  const digits = raw.replace(/\D/g, "").replace(/^1(\d{10})$/, "$1");
  if (digits.length === 10) {
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
  }
  return raw;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface SendFaxPanelProps {
  onOpenAddressBook?: () => void;
  selectedContact?: { fax: string } | null;
  onContactConsumed?: () => void;
}

export default function SendFaxPanel({
  onOpenAddressBook,
  selectedContact,
  onContactConsumed,
}: SendFaxPanelProps) {
  const [areaCode, setAreaCode] = useState("");
  const [prefix, setPrefix] = useState("");
  const [suffix, setSuffix] = useState("");
  const [callerId, setCallerId] = useState("");
  const [callerIds, setCallerIds] = useState<string[]>([]);
  const [includeCover, setIncludeCover] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [showContacts, setShowContacts] = useState(false);
  const [sending, setSending] = useState(false);

  const prefixRef = useRef<HTMLInputElement>(null);
  const suffixRef = useRef<HTMLInputElement>(null);

  // Apply contact selected from Address Book dialog
  useEffect(() => {
    if (selectedContact) {
      const num = selectedContact.fax.replace(/\D/g, "").replace(/^1(\d{10})$/, "$1");
      if (num.length === 10) {
        setAreaCode(num.slice(0, 3));
        setPrefix(num.slice(3, 6));
        setSuffix(num.slice(6, 10));
      }
      onContactConsumed?.();
    }
  }, [selectedContact]);

  // Load caller IDs and contacts
  useEffect(() => {
    invoke<{ all_fax_numbers?: string[] }>("get_app_state").then((state) => {
      const nums = state?.all_fax_numbers || [];
      setCallerIds(nums);
      if (nums.length > 0 && !callerId) setCallerId(nums[0]);
    });

    invoke<{ contacts?: Contact[] }>("get_contacts").then((result) => {
      if (result?.contacts) setContacts(result.contacts);
    });
  }, []);

  // Auto-advance on 3-digit area code
  const handleAreaChange = (val: string) => {
    const digits = val.replace(/\D/g, "");
    setAreaCode(digits);
    if (digits.length === 3) prefixRef.current?.focus();
  };

  const handlePrefixChange = (val: string) => {
    const digits = val.replace(/\D/g, "");
    setPrefix(digits);
    if (digits.length === 3) suffixRef.current?.focus();
  };

  const handleSuffixChange = (val: string) => {
    setSuffix(val.replace(/\D/g, ""));
  };

  const selectContact = (contact: Contact) => {
    const num = contact.fax.replace(/\D/g, "");
    setAreaCode(num.slice(0, 3));
    setPrefix(num.slice(3, 6));
    setSuffix(num.slice(6, 10));
    setShowContacts(false);
  };

  const removeAttachment = (index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSend = async () => {
    const fullNumber = `${areaCode}${prefix}${suffix}`;
    if (fullNumber.length !== 10) return;
    setSending(true);
    try {
      await invoke("send_fax", {
        recipient: fullNumber,
        caller_id: callerId,
        include_cover: includeCover,
        attachments: attachments.map((a) => a.name),
      });
    } catch {
      // Error will be shown by sidecar event
    } finally {
      setSending(false);
    }
  };

  const isValid = areaCode.length === 3 && prefix.length === 3 && suffix.length === 4;

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-5">
        <h2 className="text-base font-semibold mb-4 text-text-primary">
          Send Fax
        </h2>

        {/* Recipient Number */}
        <label className="block text-xs font-medium text-text-secondary mb-1.5 uppercase tracking-wide">
          Recipient Fax Number
        </label>
        <div className="flex items-center gap-1.5 mb-1">
          <input
            type="text"
            maxLength={3}
            placeholder="Area"
            value={areaCode}
            onChange={(e) => handleAreaChange(e.target.value)}
            className="w-[4.5rem] px-2 py-2 text-sm rounded-md border border-border bg-surface text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent text-center font-mono"
          />
          <span className="text-text-muted">-</span>
          <input
            ref={prefixRef}
            type="text"
            maxLength={3}
            placeholder="Prefix"
            value={prefix}
            onChange={(e) => handlePrefixChange(e.target.value)}
            className="w-[4.5rem] px-2 py-2 text-sm rounded-md border border-border bg-surface text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent text-center font-mono"
          />
          <span className="text-text-muted">-</span>
          <input
            ref={suffixRef}
            type="text"
            maxLength={4}
            placeholder="Number"
            value={suffix}
            onChange={(e) => handleSuffixChange(e.target.value)}
            className="w-[5.5rem] px-2 py-2 text-sm rounded-md border border-border bg-surface text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent text-center font-mono"
          />
        </div>

        {/* Address book shortcut */}
        <div className="mb-4">
          <div className="flex items-center gap-3 mt-1">
            {onOpenAddressBook && (
              <button
                onClick={onOpenAddressBook}
                className="px-3 py-1.5 text-sm font-medium rounded-md border border-accent text-accent hover:bg-accent hover:text-white transition-colors"
              >
                Address Book
              </button>
            )}
            <button
              onClick={() => setShowContacts(!showContacts)}
              className="px-3 py-1.5 text-sm rounded-md border border-border text-text-secondary hover:bg-background transition-colors"
            >
              {showContacts ? "Hide quick picks" : "Quick pick"}
            </button>
          </div>
          {showContacts && contacts.length > 0 && (
            <div className="mt-1.5 border border-border rounded-md bg-surface max-h-32 overflow-y-auto">
              {contacts.map((c) => (
                <button
                  key={c.id}
                  onClick={() => selectContact(c)}
                  className="w-full text-left px-3 py-1.5 text-xs hover:bg-background transition-colors flex justify-between"
                >
                  <span className="text-text-primary">{c.name}</span>
                  <span className="text-text-muted font-mono">{c.fax}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Caller ID */}
        <label className="block text-xs font-medium text-text-secondary mb-1.5 uppercase tracking-wide">
          Caller ID
        </label>
        <select
          value={callerId}
          onChange={(e) => setCallerId(e.target.value)}
          className="w-full px-3 py-2 text-sm rounded-md border border-border bg-surface text-text-primary focus:outline-none focus:ring-2 focus:ring-accent mb-4"
        >
          {callerIds.length === 0 ? (
            <option value="">No numbers available</option>
          ) : (
            callerIds.map((num) => (
              <option key={num} value={num}>
                {formatPhone(num)}
              </option>
            ))
          )}
        </select>

        {/* Cover Sheet */}
        <label className="flex items-center gap-2.5 text-sm text-text-secondary mb-4 cursor-pointer">
          <input
            type="checkbox"
            checked={includeCover}
            onChange={(e) => setIncludeCover(e.target.checked)}
            className="rounded border-border accent-accent w-4 h-4"
          />
          Include cover sheet
        </label>

        {/* Attachments area */}
        <label className="block text-xs font-medium text-text-secondary mb-1.5 uppercase tracking-wide">
          Attachments
        </label>
        <div className="border-2 border-dashed border-border rounded-lg p-6 text-center mb-3 hover:border-accent transition-colors cursor-pointer">
          <svg
            width="28"
            height="28"
            viewBox="0 0 24 24"
            fill="none"
            className="mx-auto mb-2 text-text-muted opacity-40"
          >
            <path
              d="M12 5v14M5 12h14"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
          <p className="text-sm text-text-muted">
            Drop files here or click to browse
          </p>
          <p className="text-[11px] text-text-muted mt-1">
            PDF, JPG, PNG, TIFF
          </p>
        </div>

        {/* Attachment list */}
        {attachments.length > 0 && (
          <div className="space-y-1 mb-4">
            {attachments.map((file, i) => (
              <div
                key={i}
                className="flex items-center justify-between px-3 py-1.5 bg-background rounded text-xs"
              >
                <span className="text-text-primary truncate">{file.name}</span>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-text-muted">{formatBytes(file.size)}</span>
                  <button
                    onClick={() => removeAttachment(i)}
                    className="text-error hover:text-error/80 transition-colors"
                  >
                    &times;
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Action buttons (pinned to bottom) */}
      <div className="p-5 pt-3 border-t border-border">
        <div className="flex gap-2">
          <button
            onClick={handleSend}
            disabled={!isValid || sending}
            className="flex-1 px-4 py-2.5 text-sm font-medium rounded-md bg-accent text-white hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {sending ? "Sending..." : "Send Fax"}
          </button>
          <button className="px-4 py-2.5 text-sm font-medium rounded-md bg-surface border border-border text-text-secondary hover:bg-background transition-colors">
            Scan
          </button>
        </div>
      </div>
    </div>
  );
}
