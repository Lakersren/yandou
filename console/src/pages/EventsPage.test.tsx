import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { EventData, PaginatedData, SessionData } from "../api/types";
import { renderConsole } from "../test/render";

const session: SessionData = { user: { id: 1, username: "operator" }, scheduler: "healthy" };
const events: PaginatedData<EventData> = {
  items: [{
    id: 3,
    product: { id: 1, name: "Bayou Morning" },
    site: { code: "sp", name: "Smokingpipes", region: "US" },
    variant: { id: 2, name: "2 oz" },
    price: "14.50",
    currency: "USD",
    timestamp: "2026-09-14T10:00:00+08:00",
    notifications: { total: 2, success: 2, failed: 0 },
  }],
  total: 1,
  page: 1,
  page_size: 20,
};

describe("EventsPage", () => {
  it("renders notification result counts on events", async () => {
    vi.spyOn(api, "get").mockImplementation(async <T,>(path: string) => (
      path === "session" ? session : events
    ) as T);

    renderConsole("/events");

    expect(await screen.findByText("发送成功 2/2")).toBeInTheDocument();
    expect(screen.getByText("Bayou Morning")).toBeInTheDocument();
    expect(screen.getByText("Smokingpipes")).toBeInTheDocument();
  });
});
