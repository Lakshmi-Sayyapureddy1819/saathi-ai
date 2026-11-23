import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/manrope";
import App from "./App";
import "./design/tokens.css";
import "./design/base.css";
import "./design/ui.css";
import "./design/shell.css";
import "./design/pages.css";
import "./design/chat.css";
import "./design/booking.css";
import "./design/voice.css";
import "./design/motion.css";
import "./design/mimi.css";
import "./design/insights.css";
import "./design/background.css";
import "./design/sky.css";

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
