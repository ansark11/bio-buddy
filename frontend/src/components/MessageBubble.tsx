"use client";

import { useState } from "react";
import type { ChatMessage } from "@/lib/types";

interface Props {
  message: ChatMessage;
}

export default function MessageBubble({ message }: Props) {
  const [showSources, setShowSources] = useState(false);
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] space-y-1 ${isUser ? "items-end" : "items-start"} flex flex-col`}>
        <div
          className={`px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
            isUser
              ? "bg-userbg text-white rounded-br-sm"
              : "bg-page border border-white/[0.08] text-ink rounded-bl-sm"
          }`}
        >
          {message.content}
        </div>

        {!isUser && message.sources && message.sources.length > 0 && (
          <button
            onClick={() => setShowSources(!showSources)}
            className="text-xs text-hblue hover:text-hblue/70 transition-colors font-medium"
          >
            {showSources ? "Hide" : "Show"} {message.sources.length} source{message.sources.length !== 1 ? "s" : ""} ›
          </button>
        )}

        {showSources && message.sources && (
          <div className="space-y-1 w-full">
            {message.sources.map((src, i) => (
              <div key={i} className="bg-cardhi border border-white/[0.08] rounded-lg px-3 py-2 text-xs text-muted">
                <span className="font-semibold text-muted/60 uppercase tracking-wide text-[10px]">{src.type}</span>
                <p className="mt-0.5 text-ink/70">{src.content}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
