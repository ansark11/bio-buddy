"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiClient, setToken } from "@/lib/api";
import type { AuthResponse } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit() {
    setError("");
    setLoading(true);
    try {
      const endpoint = mode === "login" ? "/api/auth/login" : "/api/auth/signup";
      const data = await apiClient.post<AuthResponse>(endpoint, { email, password });
      setToken(data.access_token);
      localStorage.setItem("auth_user", JSON.stringify({ user_id: data.user_id, email: data.email }));
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-page">
      <div className="bg-card border border-white/[0.08] rounded-xl p-8 w-full max-w-sm">
        <h1 className="font-heading font-semibold text-2xl text-center text-ink mb-1">Health RAG</h1>
        <p className="text-muted text-sm text-center mb-6">Your personal health knowledge base</p>

        <div className="flex rounded-lg overflow-hidden border border-white/[0.08] mb-6">
          <button
            onClick={() => setMode("login")}
            className={`flex-1 py-2 text-sm font-medium transition-colors ${
              mode === "login" ? "bg-hblue text-white" : "text-muted hover:text-ink hover:bg-white/5"
            }`}
          >
            Login
          </button>
          <button
            onClick={() => setMode("signup")}
            className={`flex-1 py-2 text-sm font-medium transition-colors ${
              mode === "signup" ? "bg-hblue text-white" : "text-muted hover:text-ink hover:bg-white/5"
            }`}
          >
            Sign Up
          </button>
        </div>

        <div className="space-y-3">
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            className="w-full bg-page border border-white/[0.08] text-ink placeholder-muted rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-hblue/40"
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            className="w-full bg-page border border-white/[0.08] text-ink placeholder-muted rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-hblue/40"
          />
        </div>

        {error && <p className="text-bad text-sm mt-3">{error}</p>}

        <button
          onClick={handleSubmit}
          disabled={loading || !email || !password}
          className="w-full mt-4 bg-hblue text-white rounded-lg py-2 text-sm font-medium hover:bg-hblue/80 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? "…" : mode === "login" ? "Login" : "Create Account"}
        </button>
      </div>
    </div>
  );
}
