interface StatusBarProps {
  ready: boolean;
}

export default function StatusBar({ ready }: StatusBarProps) {
  return (
    <footer className="flex items-center justify-between px-5 py-2 bg-surface border-t border-border text-xs text-text-muted no-select">
      <div className="flex items-center gap-4">
        <span>
          Backend:{" "}
          {ready ? (
            <span className="text-success">Connected</span>
          ) : (
            <span className="text-warning animate-pulse">Connecting...</span>
          )}
        </span>
        <span>Poll: Idle</span>
      </div>
      <div className="flex items-center gap-4">
        <span>Token: --:--</span>
        <span>FaxRetriever v3.0</span>
      </div>
    </footer>
  );
}
