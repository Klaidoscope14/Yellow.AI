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
      <button
        className="chat-launcher"
        onClick={() => setOpen((v) => !v)}
        aria-label="Ask about this report"
      >
        <Icon size={21} strokeWidth={1.9}>
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </Icon>
        {pending > 0 && <span className="chat-badge">{pending}</span>}
        <span className="chat-status-dot" aria-hidden />
      </button>

      {open && (
        <>
          <div className="chat-scrim" onClick={() => setOpen(false)} />
          <div className="chat-sheet">
            <div className="chat-header">
              <span>Ask about this report</span>
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

            <div className="chat-input">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !sending && send(input)}
                placeholder="Type a question&hellip;"
                autoFocus
              />
              <button disabled={!input.trim() || sending} onClick={() => send(input)}>
                Send
              </button>
            </div>
          </div>
        </>
      )}
    </>
  );
}
