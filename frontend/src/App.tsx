import { MotionConfig } from "framer-motion";
import { AppProvider, useApp } from "./app/context";
import { useRoute } from "./app/routes";
import { AppShell } from "./components/shell/AppShell";
import { ToastProvider } from "./components/ui";
import { BookingsPage } from "./pages/BookingsPage";
import { ChatPage } from "./pages/ChatPage";
import { Coordinator } from "./pages/Coordinator";
import { InsightsPage } from "./pages/InsightsPage";
import { LabsPage } from "./pages/LabsPage";
import { Overview } from "./pages/Overview";
import { SettingsPage } from "./pages/SettingsPage";
import { SupportPage } from "./pages/SupportPage";
import { VoicePage } from "./pages/VoicePage";
import { ReminderCallPage } from "./pages/ReminderCallPage";

function Routes() {
  const route = useRoute();
  const { s } = useApp();
  if (route === "coordinator") return <Coordinator />;
  return (
    <AppShell route={route}>
      {s.restoring ? <p className="muted" role="status">Restoring your session…</p> : (
        route === "overview" ? <Overview />
          : route === "chat" ? <ChatPage />
            : route === "voice" ? <VoicePage />
              : route === "reminder" ? <ReminderCallPage />
              : route === "labs" ? <LabsPage />
                : route === "bookings" ? <BookingsPage />
                  : route === "insights" ? <InsightsPage />
                    : route === "support" ? <SupportPage />
                      : <SettingsPage />
      )}
    </AppShell>
  );
}

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <ToastProvider>
        <AppProvider><Routes /></AppProvider>
      </ToastProvider>
    </MotionConfig>
  );
}
