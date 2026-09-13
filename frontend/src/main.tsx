import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ReportProvider } from "./hooks/ReportContext";
import { App } from "./App";
import "./styles/global.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter basename="/app">
      <ReportProvider>
        <App />
      </ReportProvider>
    </BrowserRouter>
  </StrictMode>,
);
