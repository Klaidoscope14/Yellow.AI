// The 11 operator asks in their own words (for the Refusals screen), and the
// role labels used on the Finding detail screen.
import type { Audience } from "../api/types";

export const ASKS: Record<string, string> = {
  A01: "What share of conversations did we handle end to end without a human?",
  A02: "Are we getting better or worse month over month?",
  A03: "Which intents cost us the most per resolved conversation?",
  A04: "How often did a tool call fail?",
  A05: "Where are people dropping out of the returns journey?",
  A06: "Is the knowledge base actually answering what people ask?",
  A07: "Did the model upgrade help or hurt?",
  A08: "How much did we spend serving customers this month, and on what?",
  A09: "How many users gave up out of frustration rather than getting what they wanted and leaving?",
  A10: "Which conversations should a human review this week?",
  A11: "What is our failover rate — how often did a primary model or tool fail and an alternate serve the user instead?",
};

export const ROLE_LABEL: Record<Audience, string> = {
  agent_builder: "Agent builder",
  business_owner: "Business owner",
  platform_owner: "Platform team",
};
