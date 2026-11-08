import { AnimatePresence, motion } from "motion/react";
import { Toaster } from "sonner";
import { Ribbon } from "./components/Ribbon";
import { StatusBar } from "./components/StatusBar";
import { TabBar } from "./components/TabBar";
import { TitleBar } from "./components/TitleBar";
import { DiagnosticsDialog } from "./dialogs/DiagnosticsDialog";
import { ExtractDialog } from "./dialogs/ExtractDialog";
import { ProgressOverlay } from "./dialogs/ProgressOverlay";
import { MessengerImportDialog } from "./dialogs/MessengerImportDialog";
import { ReportWizard } from "./dialogs/ReportWizard";
import { AboutDialog, AuditDialog, CaseDialog, HistoryDialog, NumberDialog, PickerDialog } from "./dialogs/SmallDialogs";
import { I18nProvider } from "./lib/i18n";
import { StoreProvider, useStore, type Tab } from "./lib/store";
import { CallsView } from "./views/CallsView";
import { ConnectView } from "./views/ConnectView";
import { ContactsView } from "./views/ContactsView";
import { DeviceView } from "./views/DeviceView";
import { ChatsView, SmsView } from "./views/MessagesView";
import { AppsView, NotesView, SimView, VoiceView, WebView, WifiView } from "./views/MiscViews";
import { PhotosView } from "./views/PhotosView";
import { NetworkView } from "./views/NetworkView";
import { TimelineView } from "./views/TimelineView";
import { CommsView } from "./views/CommsView";

const VIEWS: Record<Exclude<Tab, "device">, () => React.ReactNode> = {
  network: NetworkView,
  timeline: TimelineView,
  comms: CommsView,
  calls: CallsView,
  contacts: ContactsView,
  sms: SmsView,
  chats: ChatsView,
  web: WebView,
  notes: NotesView,
  voice: VoiceView,
  wifi: WifiView,
  sim: SimView,
  photos: PhotosView,
  apps: AppsView,
};

function Content() {
  const { state, tab, loaded } = useStore();
  if (!loaded) return <main className="min-h-0 flex-1" />;
  let body: React.ReactNode;
  let key: string = tab;
  if (tab === "device") {
    body = state.device ? <DeviceView /> : <ConnectView />;
    key = state.device ? "device" : "connect";
  } else {
    const View = VIEWS[tab];
    body = <View />;
  }
  return (
    <main className="min-h-0 flex-1 px-5 pt-3 pb-4">
      <AnimatePresence mode="wait">
        <motion.div
          key={key}
          className="h-full"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.18 }}
        >
          {body}
        </motion.div>
      </AnimatePresence>
    </main>
  );
}

function Shell() {
  const { theme } = useStore();
  return (
    <div className="flex h-full flex-col">
      <TitleBar />
      <Ribbon />
      <TabBar />
      <Content />
      <StatusBar />
      <ExtractDialog />
      <ProgressOverlay />
      <DiagnosticsDialog />
      <CaseDialog />
      <HistoryDialog />
      <NumberDialog />
      <PickerDialog />
      <AuditDialog />
      <AboutDialog />
      <ReportWizard />
      <MessengerImportDialog />
      <Toaster position="bottom-right" theme={theme} richColors closeButton offset={44} toastOptions={{ style: { fontFamily: "var(--font-sans)" } }} />
    </div>
  );
}

export default function App() {
  return (
    <I18nProvider>
      <StoreProvider>
        <Shell />
      </StoreProvider>
    </I18nProvider>
  );
}
