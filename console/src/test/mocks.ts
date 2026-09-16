import { vi } from "vitest";

import { api } from "../api/client";
import type { SessionData } from "../api/types";

export function mockGet<T>(value: T) {
  return vi.spyOn(api, "get").mockImplementation(async () => value);
}

export function mockPost<T>(value: T) {
  return vi.spyOn(api, "post").mockImplementation(async () => value);
}

export function mockPatch<T>(value: T) {
  return vi.spyOn(api, "patch").mockImplementation(async () => value);
}

export function mockDelete<T = void>(value: T) {
  return vi.spyOn(api, "delete").mockImplementation(async () => value);
}

export function mockSession(overrides: Partial<SessionData> = {}) {
  const session: SessionData = {
    user: { id: 1, username: "operator" },
    scheduler: "healthy",
    ...overrides,
  };
  return mockGet(session);
}
