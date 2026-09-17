import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { postChat } from "../api/client";
import { ASKS } from "../lib/asks";
import { GlassFilter } from "./GlassFilter";
import type { ChatResponse } from "../api/types";

const ASK_IDS = Object.keys(ASKS);

/** "A01" -> "A1" for the button label; keeps the zero-padded id for lookups. */
function shortLabel(id: string) {
  return `A${parseInt(id.slice(1), 10)}`;
}

interface AskState {
  loading: boolean;
  data?: ChatResponse;
  error?: boolean;
}

/** The 11 operator asks, each pulling its answer straight from the backend
 * report -- the same /chat endpoint the old "Ask Nexy" bar used, just
 * pre-bound to one fixed question per button instead of free text. */
export function AskNexusGrid() {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, AskState>>({});
  const nav = useNavigate();

  function toggle(id: string) {
    if (activeId === id) {
      setActiveId(null);
      return;
    }
    setActiveId(id);
    if (!answers[id]) {
      setAnswers((prev) => ({ ...prev, [id]: { loading: true } }));
      postChat(ASKS[id])
        .then((data) => setAnswers((prev) => ({ ...prev, [id]: { loading: false, data } })))
        .catch(() => setAnswers((prev) => ({ ...prev, [id]: { loading: false, error: true } })));
    }
  }

  function handleLink(link: ChatResponse["link"]) {
    if (!link) return;
    if (link.screen === "finding" && link.id) nav(`/finding/${link.id}`);
    else if (link.screen === "refusals") nav("/gaps");
    else if (link.screen === "dismissed") nav("/dismissed");
    setActiveId(null);
  }

  const active = activeId ? answers[activeId] : undefined;

  return (
    <section className="ask-panel-wrap">
      <p className="decision-panel-eyebrow">Ask Nexy</p>
      <div className="ask-grid">
        {ASK_IDS.map((id) => (
          <button
            key={id}
            type="button"
            className={`ask-pill${activeId === id ? " ask-pill--active" : ""}`}
            onClick={() => toggle(id)}
            aria-expanded={activeId === id}
            title={ASKS[id]}
          >
            <span className="ai-glass-layer ask-pill-glass" />
            <span className="ask-pill-orb">
              <span className="ai-orb-a" />
              <span className="ai-orb-b" />
            </span>
            <span className="ask-pill-label">{shortLabel(id)}</span>
          </button>
        ))}
      </div>

      <GlassFilter />

      <AnimatePresence>
        {activeId && (
          <>
            <motion.div
              className="chat-scrim"
              onClick={() => setActiveId(null)}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
            />
            {/* Plain (non-motion) anchor pins the popup dead-center of the
                viewport; framer-motion writes its own `transform` for the
                scale/y animation onto the inner element, which would
                otherwise clobber a CSS `translateX(-50%)` on the same
                node. */}
            <div className="ask-popup-anchor">
              <motion.div
                className="ask-popup"
                initial={{ opacity: 0, y: 12, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 12, scale: 0.97 }}
                transition={{ type: "spring", stiffness: 380, damping: 32 }}
              >
                <div className="ai-glass-layer" />
                <div className="ask-popup-body">
                  <div className="chat-header">
                    <span>{shortLabel(activeId)}</span>
                    <button className="chat-close" onClick={() => setActiveId(null)}>Close</button>
                  </div>
                  <div className="chat-log ask-popup-log">
                    <div className="msg user">{ASKS[activeId]}</div>
                    {active?.loading && <div className="msg bot muted">Thinking&hellip;</div>}
                    {active?.error && (
                      <div className="msg bot refusal-msg">Something went wrong.</div>
                    )}
                    {active?.data && (
                      <div className={`msg bot${active.data.refusal ? " refusal-msg" : ""}`}>
                        {active.data.answer}
                        {active.data.link && (
                          <button className="jump" onClick={() => handleLink(active.data!.link)}>
                            Go to {active.data.link.screen} &rsaquo;
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            </div>
          </>
        )}
      </AnimatePresence>
    </section>
  );
}
