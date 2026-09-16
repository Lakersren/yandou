import type { ApiErrorBody, ApiSuccess } from "./types";

const API_PREFIX = "/api/console/v1";

export function loginUrl(location: Pick<Location, "pathname" | "search" | "hash">): string {
  const destination = location.pathname.startsWith("/console/") || location.pathname === "/console"
    ? `${location.pathname}${location.search}${location.hash}`
    : "/console/";
  return `/admin/login/?next=${encodeURIComponent(destination)}`;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly fields?: ApiErrorBody["fields"],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function getCookie(name: string): string | undefined {
  const prefix = `${encodeURIComponent(name)}=`;
  const cookie = document.cookie.split("; ").find((item) => item.startsWith(prefix));
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : undefined;
}

function apiUrl(path: string): string {
  return `${API_PREFIX}/${path.replace(/^\/+/, "")}`;
}

async function responseBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json().catch(() => undefined);
  }
  return response.text().catch(() => undefined);
}

async function request<T>(path: string, method: string, body?: unknown): Promise<T> {
  const mutation = method !== "GET";
  const headers: Record<string, string> = { Accept: "application/json" };

  if (mutation) {
    headers["Content-Type"] = "application/json";
    const csrfToken = getCookie("csrftoken");
    if (csrfToken) {
      headers["X-CSRFToken"] = csrfToken;
    }
  }

  const response = await fetch(apiUrl(path), {
    method,
    headers,
    credentials: "same-origin",
    body: mutation && body !== undefined ? JSON.stringify(body) : undefined,
  });
  const payload = await responseBody(response);

  if (!response.ok) {
    const error = payload && typeof payload === "object" ? payload as Partial<ApiErrorBody> : {};
    if (response.status === 401) {
      window.location.href = loginUrl(window.location);
    }
    throw new ApiError(
      response.status,
      error.code ?? "request_failed",
      error.message ?? "请求失败，请稍后重试",
      error.fields,
    );
  }

  return (payload as ApiSuccess<T>).data;
}

export const api = {
  get<T>(path: string): Promise<T> {
    return request<T>(path, "GET");
  },

  post<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, "POST", body);
  },

  patch<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, "PATCH", body);
  },

  delete<T = void>(path: string): Promise<T> {
    return request<T>(path, "DELETE");
  },
};
