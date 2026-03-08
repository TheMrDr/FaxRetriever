interface HeaderProps {
  theme: "light" | "dark";
  onToggleTheme: () => void;
  sidecarReady: boolean;
  sidecarError: string | null;
  devMode: boolean;
  onVersionCheck: () => void;
  onOpenSettings: () => void;
  onOpenOutbox: () => void;
  version?: string;
}

function GearIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function OutboxIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
      <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
    </svg>
  );
}

export default function Header({
  theme,
  onToggleTheme,
  sidecarReady,
  sidecarError,
  devMode,
  onVersionCheck,
  onOpenSettings,
  onOpenOutbox,
  version,
}: HeaderProps) {
  return (
    <header className="flex items-center justify-between px-5 py-3 bg-surface border-b border-border no-select">
      {/* Left: Logo + Title */}
      <div className="flex items-center gap-3">
        <img
          src="/logo.png"
          alt="FaxRetriever"
          className="w-9 h-9 rounded-lg"
          draggable={false}
        />
        <h1 className="text-lg font-semibold text-text-primary">
          FaxRetriever
        </h1>
        {version && (
          <span className="text-xs text-text-muted ml-1">v{version}</span>
        )}
      </div>

      {/* Center: Status */}
      <div className="flex items-center gap-3">
        {devMode ? (
          <span className="text-xs text-warning font-medium px-2 py-0.5 rounded bg-warning/10">
            Dev Mode (mock data)
          </span>
        ) : sidecarError ? (
          <span className="text-xs text-error">
            Sidecar error: {sidecarError}
          </span>
        ) : !sidecarReady ? (
          <span className="text-xs text-text-muted animate-pulse">
            Starting backend...
          </span>
        ) : (
          <span className="text-xs text-success">Backend connected</span>
        )}
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-1.5">
        <button
          onClick={onVersionCheck}
          className="px-3 py-1.5 text-xs rounded-md bg-primary text-text-on-primary hover:bg-primary-hover transition-colors"
        >
          Check Version
        </button>

        <button
          onClick={onToggleTheme}
          className="px-3 py-1.5 text-xs rounded-md bg-surface border border-border text-text-secondary hover:bg-background transition-colors"
          title={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
        >
          {theme === "light" ? "Dark Mode" : "Light Mode"}
        </button>

        <button
          onClick={onOpenOutbox}
          className="p-1.5 rounded-md bg-surface border border-border text-text-secondary hover:bg-background hover:text-text-primary transition-colors"
          title="Outbox"
        >
          <OutboxIcon />
        </button>

        <button
          onClick={onOpenSettings}
          className="p-1.5 rounded-md bg-surface border border-border text-text-secondary hover:bg-background hover:text-text-primary transition-colors"
          title="Settings"
        >
          <GearIcon />
        </button>
      </div>
    </header>
  );
}
