export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const adminKey = typeof window === "undefined" ? "" : window.sessionStorage.getItem("marketpulse-admin-key") || "";
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(adminKey ? { "X-Admin-Key": adminKey } : {}), ...init?.headers },
    cache: "no-store",
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `API request failed (${response.status})`);
  return body as T;
}