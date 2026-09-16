import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { FailureData, PaginatedData, SessionData } from "../api/types";
import { renderConsole } from "../test/render";

const session: SessionData = { user: { id: 1, username: "operator" }, scheduler: "healthy" };
const failures: PaginatedData<FailureData> = {
  items: [{
    id: "crawl:12",
    kind: "crawl",
    product: { id: 1, name: "Bayou Morning" },
    site: { code: "sp", name: "Smokingpipes", region: "US" },
    message: "商品抓取失败，请稍后重试",
    occurred_at: "2026-09-14T10:00:00+08:00",
  }],
  total: 1,
  page: 1,
  page_size: 20,
};

describe("FailuresPage", () => {
  it("retries a crawl failure", async () => {
    vi.spyOn(api, "get").mockImplementation(async <T,>(path: string) => (
      path === "session" ? session : failures
    ) as T);
    const retryFailure = vi.spyOn(api, "post").mockResolvedValue({ queued: true });

    renderConsole("/failures");

    fireEvent.click(await screen.findByRole("button", { name: "重新检查" }));
    await waitFor(() => expect(retryFailure).toHaveBeenCalledWith("failures/crawl:12/retry"));
    expect(screen.getByText("抓取异常")).toBeInTheDocument();
  });
});
