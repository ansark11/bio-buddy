"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import MessageBubble from "./MessageBubble";
import { apiClient, fetchChatSessions } from "@/lib/api";
import type { ChatMessage, ChatSession } from "@/lib/types";

interface ChatResponse {
  response: string;
  sources: ChatMessage["sources"];
}

const SUGGESTED_QUESTIONS = [
  "Summarize my health data",
  "Are any of my biomarkers outside the normal range?",
  "How has my sleep been recently?",
  "What is my average daily calorie intake?",
];

function getOrCreateSessionId(): string {
  const existing = sessionStorage.getItem("chat_session_id");
  if (existing) return existing;
  const id = crypto.randomUUID();
  sessionStorage.setItem("chat_session_id", id);
  return id;
}

function dateLabel(isoString: string): string {
  const d = new Date(isoString);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86400000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return "This Week";
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: diffDays > 365 ? "numeric" : undefined });
}

function groupSessionsByDate(sessions: ChatSession[]): { label: string; items: ChatSession[] }[] {
  const groups: Record<string, ChatSession[]> = {};
  for (const s of sessions) {
    const label = dateLabel(s.created_at);
    if (!groups[label]) groups[label] = [];
    groups[label].push(s);
  }
  const order = ["Today", "Yesterday", "This Week"];
  return Object.entries(groups).sort(([a], [b]) => {
    const ai = order.indexOf(a), bi = order.indexOf(b);
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return 0;
  }).map(([label, items]) => ({ label, items }));
}

export default function ChatWindow() {
  const [sessionId, setSessionId] = useState<string>("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const id = getOrCreateSessionId();
    setSessionId(id);
    apiClient
      .get<{ messages: ChatMessage[] }>(`/api/chat/history?session_id=${id}`)
      .then((d) => setMessages(d.messages))
      .catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const loadSessions = useCallback(() => {
    setSessionsLoading(true);
    fetchChatSessions()
      .then((d) => setSessions(d.sessions))
      .catch(() => {})
      .finally(() => setSessionsLoading(false));
  }, []);

  function openHistory() {
    setShowHistory(true);
    loadSessions();
  }

  function resumeSession(session: ChatSession) {
    const sid = session.session_id;
    sessionStorage.setItem("chat_session_id", sid);
    setSessionId(sid);
    setShowHistory(false);
    setMessages([]);
    apiClient
      .get<{ messages: ChatMessage[] }>(`/api/chat/history?session_id=${sid}`)
      .then((d) => setMessages(d.messages))
      .catch(() => {});
  }

  function startNewChat() {
    const id = crypto.randomUUID();
    sessionStorage.setItem("chat_session_id", id);
    setSessionId(id);
    setMessages([]);
    setShowHistory(false);
    setError("");
  }

  async function sendMessage(text: string) {
    if (!text.trim() || loading) return;
    setInput("");
    setError("");
    setShowHistory(false);

    const userMsg: ChatMessage = {
      id: `tmp-${Date.now()}`,
      role: "user",
      content: text,
      sources: [],
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const data = await apiClient.post<ChatResponse>("/api/chat", { message: text, session_id: sessionId });
      const assistantMsg: ChatMessage = {
        id: `tmp-${Date.now() + 1}`,
        role: "assistant",
        content: data.response,
        sources: data.sources ?? [],
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to get response");
    } finally {
      setLoading(false);
    }
  }

  const grouped = groupSessionsByDate(sessions);

  return (
    <div className="flex flex-col h-full relative">

      {/* History panel (slides over chat) */}
      {showHistory && (
        <div className="absolute inset-0 bg-card z-10 flex flex-col">
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.08]">
            <span className="text-xs font-semibold text-muted uppercase tracking-widest">Chat History</span>
            <button onClick={() => setShowHistory(false)} className="text-muted hover:text-ink text-lg leading-none">✕</button>
          </div>
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4">
            {sessionsLoading && <p className="text-muted text-xs text-center pt-4">Loading…</p>}
            {!sessionsLoading && sessions.length === 0 && (
              <p className="text-muted text-xs text-center pt-4">No past sessions found.</p>
            )}
            {!sessionsLoading && grouped.map(({ label, items }) => (
              <div key={label}>
                <p className="text-[10px] font-semibold text-muted uppercase tracking-widest mb-1.5 px-1">{label}</p>
                <div className="space-y-1">
                  {items.map((s) => (
                    <button
                      key={s.session_id}
                      onClick={() => resumeSession(s)}
                      className="w-full text-left px-3 py-2.5 rounded-xl bg-page border border-white/[0.06] hover:border-hblue/30 hover:bg-cardhi transition-colors group"
                    >
                      <p className="text-sm text-ink truncate">{s.preview ?? "New conversation"}</p>
                      <p className="text-[11px] text-muted mt-0.5">{s.message_count} messages</p>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="px-4 py-3 border-t border-white/[0.08]">
            <button
              onClick={startNewChat}
              className="w-full py-2 rounded-xl bg-hblue text-white text-sm font-medium hover:bg-hblue/80 transition-colors"
            >
              + New Chat
            </button>
          </div>
        </div>
      )}

      {/* Chat header actions */}
      <div className="flex items-center justify-end gap-2 px-4 pt-2 pb-1">
        <button
          onClick={openHistory}
          className="text-[11px] text-muted hover:text-ink transition-colors font-medium"
        >
          History
        </button>
        <span className="text-white/10">|</span>
        <button
          onClick={startNewChat}
          className="text-[11px] text-muted hover:text-ink transition-colors font-medium"
        >
          New chat
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-4">
        {messages.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center h-full gap-3 pt-4">
            <p className="text-muted text-xs font-semibold uppercase tracking-widest">Suggested</p>
            <div className="flex flex-col gap-2 w-full">
              {SUGGESTED_QUESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => sendMessage(q)}
                  className="text-left text-sm bg-page border border-white/[0.08] rounded-xl px-4 py-3 hover:border-hblue/40 hover:text-ink text-ink/80 transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-page border border-white/[0.08] rounded-2xl rounded-bl-sm px-4 py-3">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-muted rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                <span className="w-2 h-2 bg-muted rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                <span className="w-2 h-2 bg-muted rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
            </div>
          </div>
        )}

        {error && <p className="text-bad text-sm text-center">{error}</p>}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-white/[0.08] p-4">
        <div className="flex items-center gap-2 bg-page border border-white/[0.08] rounded-xl px-3 py-2 focus-within:border-hblue/40 focus-within:ring-1 focus-within:ring-hblue/20 transition-all">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage(input)}
            placeholder="Ask about your health data…"
            className="flex-1 bg-transparent text-sm text-ink placeholder-muted outline-none"
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={loading || !input.trim()}
            className="w-8 h-8 bg-hblue rounded-lg flex items-center justify-center shrink-0 hover:bg-hblue/80 disabled:opacity-40 transition-colors"
          >
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
              <path d="M1 6.5h11M7 1l5 5.5-5 5.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
