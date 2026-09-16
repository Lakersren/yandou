import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import { mockSession } from "../test/mocks";
import { renderConsole } from "../test/render";
import { sessionQueryOptions } from "./ConsoleLayout";

describe("ConsoleLayout", () => {
  it("polls session health every minute while the console is open", () => {
    expect(sessionQueryOptions.refetchInterval).toBe(60_000);
    expect(sessionQueryOptions.queryKey).toEqual(["session"]);
  });

  it("shows only approved navigation modules", async () => {
    mockSession();

    renderConsole("/");

    expect(await screen.findByText("工作台")).toBeInTheDocument();
    expect(screen.getByText("商品监控")).toBeInTheDocument();
    expect(screen.getByText("补货记录")).toBeInTheDocument();
    expect(screen.getByText("异常记录")).toBeInTheDocument();
    expect(screen.getByText("飞书群")).toBeInTheDocument();
    expect(screen.queryByText("解析器")).not.toBeInTheDocument();
  });

  it("shows unhealthy scheduler status from API", async () => {
    mockSession({ scheduler: "unhealthy" });

    renderConsole("/");

    expect(await screen.findByText("调度异常")).toBeInTheDocument();
  });

  it("shows an unknown service status when the session request fails", async () => {
    vi.spyOn(api, "get").mockRejectedValue(new Error("network unavailable"));

    renderConsole("/");

    expect(await screen.findByText("服务状态未知")).toBeInTheDocument();
    expect(screen.queryByText("调度异常")).not.toBeInTheDocument();
  });
});
