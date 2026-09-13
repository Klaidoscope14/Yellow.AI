import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getChatSuggestions, postChat } from "../api/client";
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

  const send = useCallback(
    async (question: string) => {
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
    },
    [],
  );

  function handleLink(link: ChatResponse["link"]) {
    if (!link) return;
    if (link.screen === "finding" && link.id) nav(`/finding/${link.id}`);
    else if (link.screen === "refusals") nav("/gaps");
    else if (link.screen === "dismissed") nav("/dismissed");
    setOpen(false);
  }

  if (!open) {
    return (
      <button className="chat-launcher" onClick={() => setOpen(true)}>
        Ask about this report{pending > 0 ? ` · ${pending} pending` : ""}
      </button>
    );
  }

  return (
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
        />
        <button disabled={!input.trim() || sending} onClick={() => send(input)}>
          Send
        </button>
      </div>
    </div>
  );
}
