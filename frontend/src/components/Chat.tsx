import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
} from "react";
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
  const [mode, setMode] = useState<Mode>("button");
  const [input, setInput] = useState("");
  const [chatInput, setChatInput] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [chips, setChips] = useState<string[]>([]);
  const [sending, setSending] = useState(false);
  const [placeholder, setPlaceholder] = useState(0);

  const inputRef = useRef<HTMLInputElement>(null);
  const chatInputRef = useRef<HTMLInputElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const nav = useNavigate();

  useEffect(() => {
    getChatSuggestions().then(setChips).catch(() => {});
  }, []);

  useEffect(() => {
    if (mode !== "input") return;
    const id = window.setInterval(() => {
      setPlaceholder((p) => (p + 1) % PLACEHOLDERS.length);
    }, 2600);
    return () => window.clearInterval(id);
  }, [mode]);

  useEffect(() => {
    if (mode === "input") {
      const id = window.setTimeout(() => inputRef.current?.focus(), 80);
      return () => window.clearTimeout(id);
    }
    if (mode === "chat" && !sending) {
      const id = window.setTimeout(() => chatInputRef.current?.focus(), 80);
      return () => window.clearTimeout(id);
    }
  }, [mode, sending]);

  useEffect(() => {
    logRef.current?.scrollTo({
      top: logRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [msgs, sending]);

  const send = useCallback(
    async (question: string) => {
      const value = question.trim();
      if (!value || sending) return;

      setInput("");
      setChatInput("");
      setMsgs((prev) => [...prev, { role: "user", text: value }]);
      setMode("chat");
      setSending(true);

      try {
        const res = await postChat(value);
        setMsgs((prev) => [
          ...prev,
          { role: "bot", text: res.answer, refusal: res.refusal, link: res.link },
        ]);
      } catch {
        setMsgs((prev) => [
          ...prev,
          { role: "bot", text: "Something went wrong. Please try again." },
        ]);
      } finally {
        setSending(false);
      }
    },
    [sending],
  );

  const close = () => {
    setMode("button");
    setInput("");
    setChatInput("");
  };

  const handleLink = (link: ChatResponse["link"]) => {
    if (!link) return;
    if (link.screen === "finding" && link.id) nav(`/finding/${link.id}`);
    else if (link.screen === "refusals") nav("/gaps");
    else if (link.screen === "dismissed") nav("/dismissed");
    close();
  };

  const handleInputKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (input.trim()) send(input);
    }
    if (e.key === "Escape") close();
  };

  const handleChatKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (chatInput.trim()) send(chatInput);
    }
    if (e.key === "Escape") close();
  };

  return (
    <>
      <style>{`
        @keyframes nexusInputIn {
          from { opacity: 0; transform: translateX(-50%) translateY(10px) scale(.98); }
          to { opacity: 1; transform: translateX(-50%) translateY(0) scale(1); }
        }
        @keyframes nexusChatIn {
          from { opacity: 0; transform: translateX(-50%) translateY(14px) scale(.98); }
          to { opacity: 1; transform: translateX(-50%) translateY(0) scale(1); }
        }
        @keyframes nexusDot {
          0%,70%,100% { opacity:.3; transform:translateY(0); }
          35% { opacity:1; transform:translateY(-3px); }
        }
        @media (max-width:760px) {
          .nexus-window-mobile {
            left:12px !important;
            right:12px !important;
            bottom:12px !important;
            width:auto !important;
            max-width:none !important;
            height:calc(100vh - 24px) !important;
            transform:none !important;
          }
          .nexus-input-mobile {
            width:calc(100vw - 24px) !important;
            max-width:none !important;
            bottom:16px !important;
          }
          .nexus-launcher-mobile {
            bottom:16px !important;
          }
        }
      `}</style>

      <div style={css.root}>
        {mode === "button" && (
          <button
            type="button"
            className="nexus-launcher-mobile"
            onClick={() => setMode("input")}
            style={css.launcher}
            aria-label="Ask Nexus"
          >
            <span style={css.launcherIcon}>
              <Spark />
            </span>
            <span>Ask Nexus</span>
            <span style={css.launcherArrow}>
              <Icon size={15} strokeWidth={2}>
                <path d="M7 10l5 5 5-5" />
              </Icon>
            </span>
            {pending > 0 && <span style={css.badge}>{pending}</span>}
          </button>
        )}

        {mode === "input" && (
          <>
            <div style={css.backdrop} onClick={close} />
            <div className="nexus-input-mobile" style={css.inputShell}>
              <div style={css.inputInner}>
                <span style={css.inputIcon}>
                  <Spark size={20} />
                </span>

                <input
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleInputKey}
                  placeholder={PLACEHOLDERS[placeholder]}
                  aria-label="Ask Nexus"
                  style={css.input}
                />

                <button
                  type="button"
                  onClick={close}
                  style={css.iconButton}
                  aria-label="Close"
                >
                  <Icon size={17} strokeWidth={2}>
                    <path d="M6 6l12 12M18 6L6 18" />
                  </Icon>
                </button>

                <button
                  type="button"
                  onClick={() => send(input)}
                  disabled={!input.trim() || sending}
                  style={{
                    ...css.send,
                    opacity: input.trim() && !sending ? 1 : 0.3,
                  }}
                  aria-label="Send"
                >
                  <Icon size={18} strokeWidth={2.2}>
                    <path d="M5 12h14M13 6l6 6-6 6" />
                  </Icon>
                </button>
              </div>
            </div>
          </>
        )}

        {mode === "chat" && (
          <>
            <div style={css.backdrop} onClick={close} />

            <section
              className="nexus-window-mobile"
              style={css.window}
              aria-label="Nexus AI assistant"
            >
              <header style={css.header}>
                <div style={css.headerLeft}>
                  <span style={css.headerIcon}>
                    <Spark size={17} />
                  </span>

                  <div>
                    <div style={{ color: "#0e0e10", fontSize: 14, fontWeight: 750, lineHeight: 1.2 }}>
                      Nexus
                    </div>
                    <div style={{ marginTop: 3, color: "#8a8882", fontSize: 11 }}>
                      AI report assistant
                    </div>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={close}
                  style={{
                    ...css.iconButton,
                    background: "#f6f4ec",
                    color: "#6a6864",
                    border: "1px solid #ece9de",
                  }}
                  aria-label="Close chat"
                >
                  <Icon size={17} strokeWidth={2}>
                    <path d="M6 6l12 12M18 6L6 18" />
                  </Icon>
                </button>
              </header>

              {chips.length > 0 && (
                <div style={css.suggestions}>
                  {chips.map((chip) => (
                    <button
                      type="button"
                      key={chip}
                      onClick={() => send(chip)}
                      disabled={sending}
                      style={{ ...css.chip, opacity: sending ? 0.45 : 1 }}
                    >
                      {chip}
                    </button>
                  ))}
                </div>
              )}

              <div ref={logRef} style={css.messages}>
                {msgs.length === 0 && (
                  <div style={{ width: 300, maxWidth: "100%", margin: "auto", textAlign: "center" }}>
                    <div
                      style={{
                        width: 48,
                        height: 48,
                        margin: "0 auto 13px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        borderRadius: "50%",
                        background: "#fff6cf",
                        color: "#201a00",
                      }}
                    >
                      <Spark size={23} />
                    </div>

                    <h3 style={{ margin: "0 0 6px", color: "#0e0e10", fontSize: 15, fontWeight: 700 }}>
                      What do you want to know?
                    </h3>

                    <p style={{ margin: 0, color: "#6a6864", fontSize: 12.5, lineHeight: 1.55 }}>
                      Ask Nexus about findings, risks, trends, or what needs attention.
                    </p>
                  </div>
                )}

                {msgs.map((msg, i) => (
                  <div
                    key={`${msg.role}-${i}`}
                    style={{
                      display: "flex",
                      gap: 8,
                      maxWidth: "90%",
                      alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
                    }}
                  >
                    {msg.role === "bot" && (
                      <span style={css.messageIcon}>
                        <Spark size={13} />
                      </span>
                    )}

                    <div
                      style={
                        msg.role === "user"
                          ? {
                              padding: "10px 13px",
                              borderRadius: 14,
                              borderBottomRightRadius: 4,
                              background: "#0e0e10",
                              color: "#fff",
                              fontSize: 13.5,
                              lineHeight: 1.5,
                              overflowWrap: "anywhere",
                              whiteSpace: "pre-line",
                            }
                          : {
                              padding: "10px 13px",
                              borderRadius: 14,
                              borderBottomLeftRadius: 4,
                              border: "1px solid #ece9de",
                              background: "#f6f4ec",
                              color: "#0e0e10",
                              fontSize: 13.5,
                              lineHeight: 1.5,
                              overflowWrap: "anywhere",
                              whiteSpace: "pre-line",
                            }
                      }
                    >
                      <div>{msg.text}</div>

                      {msg.link && (
                        <button
                          type="button"
                          onClick={() => handleLink(msg.link!)}
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 5,
                            marginTop: 8,
                            padding: 0,
                            border: 0,
                            background: "transparent",
                            color: "#0e0e10",
                            fontSize: 12,
                            fontWeight: 700,
                            cursor: "pointer",
                            textDecoration: "underline",
                            textDecorationColor: "#ffce00",
                            textUnderlineOffset: 3,
                          }}
                        >
                          Go to {msg.link.screen}
                          <Icon size={13} strokeWidth={2}>
                            <path d="M5 12h14M13 6l6 6-6 6" />
                          </Icon>
                        </button>
                      )}
                    </div>
                  </div>
                ))}

                {sending && (
                  <div style={{ display: "flex", gap: 8, alignSelf: "flex-start" }}>
                    <span style={css.messageIcon}>
                      <Spark size={13} />
                    </span>

                    <div
                      style={{
                        minWidth: 56,
                        height: 38,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: 4,
                        padding: "0 12px",
                        border: "1px solid #ece9de",
                        borderRadius: 14,
                        borderBottomLeftRadius: 4,
                        background: "#f6f4ec",
                      }}
                    >
                      {[0, 1, 2].map((d) => (
                        <span
                          key={d}
                          style={{
                            width: 5,
                            height: 5,
                            borderRadius: "50%",
                            background: "#8a8882",
                            animation: "nexusDot 1.1s infinite ease-in-out",
                            animationDelay: `${d * 0.12}s`,
                          }}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div style={css.composer}>
                <input
                  ref={chatInputRef}
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={handleChatKey}
                  placeholder="Ask a follow-up…"
                  disabled={sending}
                  aria-label="Ask a follow-up"
                  style={css.composerInput}
                />

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
