import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { DashboardData, SessionData } from "../api/types";
import { renderConsole } from "../test/render";

const dashboard: DashboardData = {
  monitored_products: 12,
  in_stock_variants: 3,
  restocks_24h: 2,
  failures_24h: 1,
  active_failures: 1,
  recent_products: [
    {
      id: 1,
      name: "Cornell & Diehl Bayou Morning",
      url: "https://example.test/products/bayou-morning",
      site: { name: "SP", region: "US" },
      stock_status: "in_stock",
      enabled: true,
      last_checked_at: "2026-09-14T10:00:00+08:00",
    },
  ],
  recent_events: [
    {
      id: 1,
      product: { id: 1, name: "Cornell & Diehl Bayou Morning", site_name: "SP" },
      variant: { id: 1, name: "2 oz" },
      new_status: "in_stock",
      price: "14.50",
      currency: "USD",
      created_at: "2026-09-14T10:00:00+08:00",
    },
  ],
  recent_failures: [
    {
      id: "crawl:1",
      kind: "crawl",
      product: { id: 1, name: "Old Holborn", site_name: "SP" },
      message: "商品抓取失败，请稍后重试",
      occurred_at: "2026-09-14T09:00:00+08:00",
    },
  ],
  pending_failures: [
    {
      id: "crawl:1",
      kind: "crawl",
      product: { id: 1, name: "Old Holborn", site_name: "SP" },
      message: "商品抓取失败，请稍后重试",
      occurred_at: "2026-09-14T09:00:00+08:00",
    },
  ],
  region_summaries: [
    {
      region: "US",
      label: "美站",
      monitored_products: 1,
      in_stock_variants: 1,
      restocks_24h: 1,
      failures_24h: 1,
      active_failures: 1,
      last_checked_at: "2026-09-14T10:00:00+08:00",
      products: [
        {
          id: 1,
          name: "Cornell & Diehl Bayou Morning",
          url: "https://example.test/products/bayou-morning",
          site: { name: "SP", region: "US" },
          stock_status: "in_stock",
          enabled: true,
          last_checked_at: "2026-09-14T10:00:00+08:00",
        },
      ],
    },
    { region: "DE", label: "德站", monitored_products: 0, in_stock_variants: 0, restocks_24h: 0, failures_24h: 0, active_failures: 0, last_checked_at: null, products: [] },
    { region: "HK", label: "港站", monitored_products: 0, in_stock_variants: 0, restocks_24h: 0, failures_24h: 0, active_failures: 0, last_checked_at: null, products: [] },
    { region: "SG", label: "新加坡站", monitored_products: 0, in_stock_variants: 0, restocks_24h: 0, failures_24h: 0, active_failures: 0, last_checked_at: null, products: [] },
    { region: "UK", label: "英站", monitored_products: 0, in_stock_variants: 0, restocks_24h: 0, failures_24h: 0, active_failures: 0, last_checked_at: null, products: [] },
  ],
};

describe("DashboardPage", () => {
  it("shows global statistics, station summaries and pending failures", async () => {
    const session: SessionData = { user: { id: 1, username: "operator" }, scheduler: "healthy" };
    vi.spyOn(api, "get").mockImplementation(async <T,>(path: string) => {
      return (path === "session" ? session : dashboard) as T;
    });

    renderConsole("/");

    expect((await screen.findAllByText("监控商品")).length).toBeGreaterThan(1);
    expect(screen.queryByText("当前现货规格")).not.toBeInTheDocument();
    expect(screen.getByText("24 小时补货")).toBeInTheDocument();
    expect(screen.getAllByText("当前异常").length).toBeGreaterThan(1);
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("Cornell & Diehl Bayou Morning")).toBeInTheDocument();
    expect(screen.getByText("有货")).toBeInTheDocument();
    expect(screen.getByText("站点概览")).toBeInTheDocument();
    expect(screen.getByText("全部站点商品状态")).toBeInTheDocument();
    expect(screen.getByText("待处理异常")).toBeInTheDocument();
    expect(screen.getByText("Old Holborn")).toBeInTheDocument();
    expect(screen.queryByText("最近补货")).not.toBeInTheDocument();
  });

  it("filters the product table when a station is selected", async () => {
    const session: SessionData = { user: { id: 1, username: "operator" }, scheduler: "healthy" };
    vi.spyOn(api, "get").mockImplementation(async <T,>(path: string) => (
      path === "session" ? session : dashboard
    ) as T);

    renderConsole("/");

    fireEvent.click(await screen.findByRole("button", { name: /德站/ }));
    expect(screen.getByText("德站商品状态")).toBeInTheDocument();
    expect(screen.queryByText("Cornell & Diehl Bayou Morning")).not.toBeInTheDocument();
    expect(screen.getByText("查看全部站点")).toBeInTheDocument();
  });

  it("submits a retry from the pending failure row", async () => {
    const session: SessionData = { user: { id: 1, username: "operator" }, scheduler: "healthy" };
    vi.spyOn(api, "get").mockImplementation(async <T,>(path: string) => (
      path === "session" ? session : dashboard
    ) as T);
    const post = vi.spyOn(api, "post").mockResolvedValue({ queued: true });

    renderConsole("/");

    fireEvent.click(await screen.findByRole("button", { name: /重新检查/ }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("failures/crawl:1/retry"));
  }, 15_000);
});
