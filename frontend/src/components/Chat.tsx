import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getChatSuggestions, postChat } from "../api/client";
import { Icon } from "./Icon";
import type { ChatResponse } from "../api/types";

interface Msg {
  role: "user" | "bot";
  text: string;
  refusal?: boolean;
  link?: ChatResponse["link"];
}

type Mode = "button" | "input" | "chat";

const PLACEHOLDERS = [
  "Ask Nexus anything…",
  "What needs attention?",
  "Why did this happen?",
  "Show me the biggest risk…",
  "What should I fix first?",
];

const font =
  'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';

const css = {
  root: {
    position: "relative",
    zIndex: 9999,
  } as CSSProperties,

  launcher: {
    position: "fixed",
    left: "50%",
    bottom: 24,
    transform: "translateX(-50%)",
    zIndex: 9999,
    width: 154,
    height: 48,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 9,
    padding: "0 12px 0 10px",
    margin: 0,
    border: "1px solid rgba(255,255,255,.14)",
    borderRadius: 999,
    background: "#0e0e10",
    color: "#fff",
    fontFamily: font,
    fontSize: 13,
    fontWeight: 650,
    lineHeight: 1,
    cursor: "pointer",
    boxShadow: "0 12px 35px rgba(0,0,0,.20), 0 3px 10px rgba(0,0,0,.12)",
    appearance: "none",
    WebkitAppearance: "none",
    outline: "none",
    transition: "transform .18s cubic-bezier(.22,1,.36,1), background .18s ease",
  } as CSSProperties,

  launcherIcon: {
    width: 28,
    height: 28,
    minWidth: 28,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: "50%",
    background: "#ffce00",
    color: "#201a00",
  } as CSSProperties,

  launcherArrow: {
    width: 20,
    height: 20,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "rgba(255,255,255,.48)",
  } as CSSProperties,

  badge: {
    position: "absolute",
    top: -6,
    right: -6,
    minWidth: 21,
    height: 21,
    padding: "0 5px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    border: "2px solid #fbfaf6",
    borderRadius: 999,
    background: "#ffce00",
    color: "#201a00",
    fontFamily: font,
    fontSize: 10,
    fontWeight: 800,
  } as CSSProperties,

  backdrop: {
    position: "fixed",
    inset: 0,
    zIndex: 9998,
    background: "rgba(14,14,16,.16)",
    backdropFilter: "blur(3px)",
    WebkitBackdropFilter: "blur(3px)",
  } as CSSProperties,

  inputShell: {
    position: "fixed",
    left: "50%",
    bottom: 24,
    transform: "translateX(-50%)",
    zIndex: 9999,
    width: 520,
    maxWidth: "calc(100vw - 32px)",
    height: 60,
    padding: 1,
    borderRadius: 999,
    background: "#0e0e10",
    boxShadow: "0 16px 55px rgba(0,0,0,.24), 0 5px 18px rgba(0,0,0,.12)",
    animation: "nexusInputIn .22s cubic-bezier(.22,1,.36,1)",
  } as CSSProperties,

  inputInner: {
    width: "100%",
    height: "100%",
    boxSizing: "border-box",
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "6px 6px 6px 19px",
    borderRadius: 999,
    background: "#0e0e10",
  } as CSSProperties,

  inputIcon: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#ffce00",
    flexShrink: 0,
  } as CSSProperties,

  input: {
    flex: "1 1 auto",
    minWidth: 0,
    width: "auto",
    height: "100%",
    margin: 0,
    padding: 0,
    border: 0,
    outline: 0,
    background: "transparent",
    color: "#fff",
    fontFamily: font,
    fontSize: 15,
    fontWeight: 450,
    boxShadow: "none",
  } as CSSProperties,

  iconButton: {
    width: 34,
    height: 34,
    minWidth: 34,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 0,
    border: 0,
    borderRadius: "50%",
    background: "transparent",
    color: "rgba(255,255,255,.45)",
    cursor: "pointer",
  } as CSSProperties,

  send: {
    width: 46,
    height: 46,
    minWidth: 46,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 0,
    border: 0,
    borderRadius: "50%",
    background: "#ffce00",
    color: "#201a00",
    cursor: "pointer",
  } as CSSProperties,

  window: {
    position: "fixed",
    left: "50%",
    bottom: 24,
    transform: "translateX(-50%)",
    zIndex: 9999,
    width: 520,
    maxWidth: "calc(100vw - 32px)",
    height: "min(600px, calc(100vh - 48px))",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    background: "#fff",
    border: "1px solid #ece9de",
    borderRadius: 20,
    boxShadow: "0 28px 80px rgba(14,14,16,.20), 0 8px 24px rgba(14,14,16,.10)",
    animation: "nexusChatIn .24s cubic-bezier(.22,1,.36,1)",
  } as CSSProperties,

  header: {
    flex: "0 0 auto",
    height: 64,
    boxSizing: "border-box",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "0 15px 0 17px",
    borderBottom: "1px solid #ece9de",
    background: "#fff",
  } as CSSProperties,

  headerLeft: {
    display: "flex",
    alignItems: "center",
    gap: 10,
  } as CSSProperties,

  headerIcon: {
    width: 34,
    height: 34,
    minWidth: 34,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: "50%",
    background: "#ffce00",
    color: "#201a00",
  } as CSSProperties,

  messages: {
    flex: "1 1 auto",
    minHeight: 0,
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    gap: 14,
    padding: 16,
    background: "#fff",
  } as CSSProperties,

  suggestions: {
    flex: "0 0 auto",
    display: "flex",
    gap: 6,
    overflowX: "auto",
    padding: "10px 14px",
    borderBottom: "1px solid #ece9de",
    background: "#fff",
  } as CSSProperties,

  chip: {
    flex: "0 0 auto",
    padding: "7px 11px",
    border: "1px solid #ece9de",
    borderRadius: 999,
    background: "#f6f4ec",
    color: "#6a6864",
    fontFamily: font,
    fontSize: 11.5,
    fontWeight: 600,
    cursor: "pointer",
    whiteSpace: "nowrap",
  } as CSSProperties,

  composer: {
    flex: "0 0 auto",
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "10px 12px",
    borderTop: "1px solid #ece9de",
    background: "#fff",
  } as CSSProperties,

  composerInput: {
    flex: "1 1 auto",
    minWidth: 0,
    height: 40,
    boxSizing: "border-box",
    padding: "0 12px",
    border: "1px solid #ece9de",
    borderRadius: 10,
    outline: 0,
    background: "#f6f4ec",
    color: "#0e0e10",
    fontFamily: font,
    fontSize: 13,
  } as CSSProperties,

  messageIcon: {
    width: 27,
    height: 27,
    minWidth: 27,
    alignSelf: "flex-end",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: "50%",
    background: "#ffce00",
    color: "#201a00",
  } as CSSProperties,

  composerSend: {
    width: 40,
    height: 40,
    minWidth: 40,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 0,
    border: 0,
    borderRadius: "50%",
    background: "#ffce00",
    color: "#201a00",
    cursor: "pointer",
  } as CSSProperties,
};

function Spark({ size = 18 }: { size?: number }) {
  return (
    <Icon size={size} strokeWidth={1.8}>
      <path d="M12 2v4m0 12v4M2 12h4m12 0h4" />
      <circle cx="12" cy="12" r="3" />
      <path d="M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M19.07 4.93l-2.83 2.83M7.76 16.24l-2.83 2.83" />
    </Icon>
  );
}

export function Chat({ pending }: { pending: number }) {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [chips, setChips] = useState<string[]>([]);
  const logRef = useRef<HTMLDivElement>(null);
  const nav = useNavigate();

  useEffect(() => {
    getChatSuggestions().then(setChips).catch(() => {});
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo(0, logRef.current.scrollHeight);
  }, [msgs]);

  const send = useCallback(async (question: string) => {
    if (!question.trim()) return;
    setMsgs((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setSending(true);
    try {
      const res = await postChat(question);
      setMsgs((prev) => [
        ...prev,
        { role: "bot", text: res.answer, refusal: res.refusal, link: res.link },
      ]);
    } catch {
      setMsgs((prev) => [...prev, { role: "bot", text: "Something went wrong." }]);
    } finally {
      setSending(false);
    }
  }, []);

  function handleLink(link: ChatResponse["link"]) {
    if (!link) return;
    if (link.screen === "finding" && link.id) nav(`/finding/${link.id}`);
    else if (link.screen === "refusals") nav("/gaps");
    else if (link.screen === "dismissed") nav("/dismissed");
    setOpen(false);
  }

  return (
    <>
      {/* Center-bottom floating launcher, Yellow.ai "Talk to Alex"-style —
          avatar + speech-bubble copy + waveform icon. On hover it lifts. */}
      <button
        className="chat-launcher"
        onClick={() => setOpen((v) => !v)}
        aria-label="Ask about this report"
      >
        <span className="chat-launcher-hint">Ask a question</span>
        <span className="chat-launcher-pill">
          <span className="chat-avatar">
            <Icon size={17} strokeWidth={2}>
              <circle cx="12" cy="8" r="4" />
              <path d="M4 21c0-4 4-6 8-6s8 2 8 6" />
            </Icon>
          </span>
          <span className="chat-launcher-copy">Nexus</span>
          <span className="chat-launcher-wave" aria-hidden>
            <span></span><span></span><span></span><span></span>
          </span>
          {pending > 0 && <span className="chat-badge">{pending}</span>}
        </span>
      </button>

      {open && (
        <>
          <div className="chat-scrim" onClick={() => setOpen(false)} />
          <div className="chat-sheet">
            <div className="chat-header">
              <span>Nexus</span>
              <button className="chat-close" onClick={() => setOpen(false)}>Close</button>
            </div>

            {chips.length > 0 && (
              <div className="chat-chips">
                {chips.map((c) => (
                  <button key={c} className="chip" onClick={() => send(c)}>
                    {c}
                  </button>
                ))}
              </div>
            )}

            <div className="chat-log" ref={logRef}>
              {msgs.length === 0 && (
                <p className="muted small" style={{ textAlign: "center", padding: 20 }}>
                  Ask a question about the report. Answers come from computed data only.
                </p>
              )}
              {msgs.map((m, i) => (
                <div key={i} className={`msg ${m.role}${m.refusal ? " refusal-msg" : ""}`}>
                  {m.text}
                  {m.link && (
                    <button className="jump" onClick={() => handleLink(m.link!)}>
                      Go to {m.link.screen} &rsaquo;
                    </button>
                  )}
                </div>
              ))}
              {sending && <div className="msg bot muted">Thinking&hellip;</div>}
            </div>

                <button
                  type="button"
                  onClick={() => send(chatInput)}
                  disabled={!chatInput.trim() || sending}
                  style={{
                    ...css.composerSend,
                    opacity: chatInput.trim() && !sending ? 1 : 0.35,
                  }}
                  aria-label="Send"
                >
                  <Icon size={17} strokeWidth={2.2}>
                    <path d="M5 12h14M13 6l6 6-6 6" />
                  </Icon>
                </button>
              </div>
            </section>
          </>
        )}
      </div>
    </>
  );
}
