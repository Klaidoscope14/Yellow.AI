import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { getChatSuggestions, postChat } from "../api/client";
import { Icon } from "./Icon";
import type { ChatResponse } from "../api/types";

const MAX_BAR_HEIGHT = 160;

/** Turbulence + displacement map: the refraction behind the glass. */
function GlassFilter() {
  return (
    <svg className="ai-glass-defs" aria-hidden>
      <defs>
        <filter id="ai-glass" x="0%" y="0%" width="100%" height="100%" colorInterpolationFilters="sRGB">
          <feTurbulence type="fractalNoise" baseFrequency="0.012 0.012" numOctaves="2" seed="4" result="noise" />
          <feGaussianBlur in="noise" stdDeviation="2" result="blurredNoise" />
          <feDisplacementMap
            in="SourceGraphic"
            in2="blurredNoise"
            scale="24"
            xChannelSelector="R"
            yChannelSelector="B"
            result="displaced"
          />
          <feGaussianBlur in="displaced" stdDeviation="0.4" />
        </filter>
      </defs>
    </svg>
  );
}

interface Msg {
  role: "user" | "bot";
  text: string;
  refusal?: boolean;
  link?: ChatResponse["link"];
}

export function Chat() {
  const [mode, setMode] = useState<"bar" | "chat">("bar");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [chips, setChips] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const nav = useNavigate();

  useEffect(() => {
    getChatSuggestions().then(setChips).catch(() => {});
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo(0, logRef.current.scrollHeight);
  }, [msgs]);

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    // Empty textarea: don't measure at all. scrollHeight read right as the
    // panel mounts (shell still mid CSS-expand from the collapsed pill) is
    // unreliable and was the source of the oversized-on-open bug — clearing
    // the inline height lets CSS size a single empty line correctly on its
    // own, no JS measurement needed for that trivial case.
    if (!input) {
      el.style.height = "";
      return;
    }
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_BAR_HEIGHT)}px`;
  }, [input, open]);

  const send = useCallback(async (question: string) => {
    if (!question.trim()) return;
    setMsgs((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setSending(true);
    setMode("chat");
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

  // The only way the shell fully collapses back to the "Ask AI" pill: one
  // call resets mode + open + input together, so every close path (the
  // header button, the scrim, Escape) produces a single clean transition
  // instead of two states drifting out of sync and needing a second click.
  function closeAll() {
    setMode("bar");
    setOpen(false);
    setInput("");
  }

  function handleLink(link: ChatResponse["link"]) {
    if (!link) return;
    if (link.screen === "finding" && link.id) nav(`/finding/${link.id}`);
    else if (link.screen === "refusals") nav("/gaps");
    else if (link.screen === "dismissed") nav("/dismissed");
    closeAll();
  }

  return (
    <>
      {/* ── "Ask AI" pill that morphs into the input panel ── */}
      <div className="ai-bar">
        <div
          className={`ai-shell${open ? " ai-shell--open" : ""}${
            mode === "chat" ? " ai-shell--chat" : ""
          }`}
        >
          <div className="ai-glass-layer" />

          {/* conversation grows upward out of the bar */}
          <AnimatePresence initial={false}>
            {mode === "chat" && (
              <motion.div
                key="chat-region"
                className="ai-chat-region"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1, transition: { duration: 0.22, delay: 0.14 } }}
                exit={{ opacity: 0, transition: { duration: 0.12 } }}
              >
                <div className="chat-header">
                  <span>Nexus</span>
                  <button className="chat-close" onClick={closeAll}>Close</button>
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
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence initial={false}>
            {open ? (
              <motion.div
                key="panel"
                className="ai-panel-body"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1, transition: { duration: 0.14 } }}
                exit={{ opacity: 0, transition: { duration: 0.1 } }}
              >
                <div className="ai-bar-main">
                  <span className="ai-orb">
                    <span className="ai-orb-a" />
                    <span className="ai-orb-b" />
                  </span>

                  <textarea
                    ref={(el) => {
                      inputRef.current = el;
                      // AnimatePresence mode="wait" doesn't mount this node
                      // until the collapsed trigger finishes exiting, so a
                      // useEffect keyed on `open` fires before it exists and
                      // the focus silently no-ops. Focusing here, on the
                      // node's actual mount, always lands correctly.
                      if (el && open) el.focus();
                    }}
                    rows={1}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onBlur={() => {
                      if (!input.trim() && mode !== "chat") setOpen(false);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Escape") {
                        closeAll();
                      } else if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        if (!sending && input.trim()) send(input);
                      }
                    }}
                    placeholder="Ask Nexus anything…"
                    aria-label="Ask about this report"
                  />

                  <button
                    className="ai-bar-send"
                    disabled={!input.trim() || sending}
                    onClick={() => send(input)}
                    aria-label="Send"
                  >
                    <Icon size={18} strokeWidth={2.2}>
                      <path d="M5 12h14M12 5l7 7-7 7" />
                    </Icon>
                  </button>
                </div>

                <div className="ai-bar-toolbar">
                  <span className="ai-bar-tools">
                    <button className="ai-tool" aria-label="Attach a file" title="Attach a file">
                      <Icon size={15}>
                        <path d="M21.44 11.05l-8.49 8.49a5.5 5.5 0 0 1-7.78-7.78l8.49-8.49a3.5 3.5 0 0 1 4.95 4.95l-8.49 8.49a1.5 1.5 0 0 1-2.12-2.12l7.78-7.78" />
                      </Icon>
                    </button>
                    <button className="ai-tool" aria-label="Voice input" title="Voice input">
                      <Icon size={15}>
                        <rect x="9" y="2" width="6" height="11" rx="3" />
                        <path d="M5 10v1a7 7 0 0 0 14 0v-1M12 18v4M8 22h8" />
                      </Icon>
                    </button>
                    <button className="ai-tool" aria-label="Emoji" title="Emoji">
                      <Icon size={15}>
                        <circle cx="12" cy="12" r="9" />
                        <path d="M8.5 14.5a4.5 4.5 0 0 0 7 0" />
                        <path d="M9 9.5h.01M15 9.5h.01" />
                      </Icon>
                    </button>
                  </span>

                  <span className="ai-bar-hint">Shift + Enter for a new line</span>
                  {input && (
                    <button
                      className="ai-bar-clear"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => {
                        setInput("");
                        inputRef.current?.focus();
                      }}
                      aria-label="Clear input"
                    >
                      <Icon size={13} strokeWidth={2.4}>
                        <path d="M18 6 6 18M6 6l12 12" />
                      </Icon>
                    </button>
                  )}
                </div>
              </motion.div>
            ) : (
              <motion.button
                key="trigger"
                className="ai-trigger"
                onClick={() => setOpen(true)}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1, transition: { duration: 0.14 } }}
                exit={{ opacity: 0, transition: { duration: 0.1 } }}
                aria-expanded={false}
              >
                <span className="ai-orb">
                  <span className="ai-orb-a" />
                  <span className="ai-orb-b" />
                </span>
                Ask AI
              </motion.button>
            )}
          </AnimatePresence>
        </div>

        <GlassFilter />
      </div>

      {mode === "chat" && <div className="chat-scrim" onClick={closeAll} />}
    </>
  );
}
