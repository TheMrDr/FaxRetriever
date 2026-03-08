import { useState } from "react";
import { useTheme } from "./hooks/useTheme";
import { useSidecarLifecycle, useSidecarInvoke } from "./hooks/useSidecar";
import Header from "./components/Header";
import SendFaxPanel from "./components/SendFaxPanel";
import FaxHistoryPanel from "./components/FaxHistoryPanel";
import StatusBar from "./components/StatusBar";
import SettingsDialog from "./components/SettingsDialog";
import AddressBookDialog from "./components/AddressBookDialog";
import OutboxPanel from "./components/OutboxPanel";

function App() {
  const { theme, toggleTheme, setTheme } = useTheme();
  const { ready, error: sidecarError, devMode } = useSidecarLifecycle();
  const { invoke, data: versionData } = useSidecarInvoke<{
    version: string;
  }>();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [addressBookOpen, setAddressBookOpen] = useState(false);
  const [outboxOpen, setOutboxOpen] = useState(false);
  const [selectedContact, setSelectedContact] = useState<{
    fax: string;
  } | null>(null);

  const handleVersionCheck = async () => {
    try {
      await invoke("get_version");
    } catch {
      // Error handled by the hook
    }
  };

  return (
    <div className="flex flex-col h-screen bg-background text-text-primary">
      {/* Header */}
      <Header
        theme={theme}
        onToggleTheme={toggleTheme}
        sidecarReady={ready}
        sidecarError={sidecarError}
        devMode={devMode}
        onVersionCheck={handleVersionCheck}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenOutbox={() => setOutboxOpen(true)}
        version={versionData?.version}
      />

      {/* Main Content */}
      <div className="flex flex-1 min-h-0">
        {/* Send Fax Panel */}
        <div className="w-[400px] shrink-0 border-r border-border">
          <SendFaxPanel
            onOpenAddressBook={() => setAddressBookOpen(true)}
            selectedContact={selectedContact}
            onContactConsumed={() => setSelectedContact(null)}
          />
        </div>

        {/* Fax History Panel */}
        <div className="flex-1 overflow-hidden">
          <FaxHistoryPanel />
        </div>
      </div>

      {/* Status Bar */}
      <StatusBar ready={ready} />

      {/* Settings Dialog */}
      <SettingsDialog
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        currentTheme={theme}
        onThemeChange={setTheme}
      />

      {/* Address Book Dialog */}
      <AddressBookDialog
        open={addressBookOpen}
        onClose={() => setAddressBookOpen(false)}
        onSelect={(contact) => {
          setSelectedContact(contact);
          setAddressBookOpen(false);
        }}
      />

      {/* Outbox Dialog */}
      <OutboxPanel
        open={outboxOpen}
        onClose={() => setOutboxOpen(false)}
      />
    </div>
  );
}

export default App;
