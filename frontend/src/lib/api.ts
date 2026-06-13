const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("auth_token");
}

export function setToken(token: string): void {
  localStorage.setItem("auth_token", token);
}

export function clearToken(): void {
  localStorage.removeItem("auth_token");
  localStorage.removeItem("auth_user");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const data = await res.json();
  if (!res.ok) {
    throw new Error((data as { detail?: string }).detail ?? `Request failed: ${res.status}`);
  }
  return data as T;
}

export const apiClient = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, formData: FormData) =>
    request<T>(path, { method: "POST", body: formData }),
};

export function uploadWithProgress<T>(
  path: string,
  formData: FormData,
  onTransferProgress: (pct: number) => void,
  onTransferComplete: () => void,
): Promise<T> {
  const token = getToken();
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}${path}`);
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        onTransferProgress(Math.round((e.loaded / e.total) * 50));
      }
    };

    xhr.upload.onload = () => {
      onTransferComplete();
    };

    xhr.onload = () => {
      let data: unknown;
      try { data = JSON.parse(xhr.responseText); } catch { reject(new Error("Invalid response")); return; }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data as T);
      } else {
        const detail = (data as { detail?: string | { message?: string } }).detail;
        const msg = typeof detail === "object" ? JSON.stringify(detail) : (detail ?? `Request failed: ${xhr.status}`);
        reject(new Error(msg));
      }
    };

    xhr.onerror = () => reject(new Error("Network error"));
    xhr.send(formData);
  });
}

export function fetchInsights(): Promise<{ insight: string; generated_at: string }> {
  return apiClient.get("/api/metrics/insights");
}

export function fetchChatSessions(): Promise<{ sessions: import("./types").ChatSession[] }> {
  return apiClient.get("/api/chat/sessions");
}
