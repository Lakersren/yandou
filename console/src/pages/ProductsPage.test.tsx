import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { PaginatedData, ProductData, SessionData } from "../api/types";
import { renderConsole } from "../test/render";
import { productListPath } from "./ProductsPage";

const activeProduct: ProductData = {
  id: 1,
  name: "Cornell & Diehl Bayou Morning",
  url: "https://smokingpipes.com/p/bayou-morning",
  site: { code: "sp", name: "Smokingpipes", region: "US" },
  stock_status: "in_stock",
  enabled: true,
  last_checked_at: "2026-09-14T10:00:00+08:00",
  variants: [{ id: 1, name: "2 oz", price: "14.50", currency: "USD", status: "in_stock" }],
  snapshots: Array.from({ length: 21 }, (_, index) => ({
    variant_name: `观察规格 ${index + 1}`,
    observed_status: index % 2 === 0 ? "in_stock" : "out_of_stock",
    price: "14.50",
    currency: "USD",
    checked_at: "2026-09-14T10:00:00+08:00",
  })),
};

const pausedProduct: ProductData = {
  ...activeProduct,
  id: 2,
  name: "Paused Product",
  enabled: false,
  stock_status: "out_of_stock",
};

const session: SessionData = { user: { id: 1, username: "operator" }, scheduler: "healthy" };
const products: PaginatedData<ProductData> = { items: [activeProduct, pausedProduct], total: 2, page: 1, page_size: 20 };
function mockProducts() {
  return vi.spyOn(api, "get").mockImplementation(async <T,>(path: string) => {
    if (path === "session") return session as T;
    if (path.startsWith("products/")) return activeProduct as T;
    return products as T;
  });
}

describe("ProductsPage", () => {
  it.each(["created", "restored"])("shows a %s product first after adding from page 2 with an incompatible filter", async (outcome) => {
    const addedProduct = { ...activeProduct, id: 99, name: "Freshly monitored product" };
    let added = false;
    const get = vi.spyOn(api, "get").mockImplementation(async <T,>(path: string) => {
      if (path === "session") return session as T;
      const params = new URLSearchParams(path.split("?")[1]);
      const visible = added && !params.has("q") && !params.has("site") && !params.has("status") && params.get("page") === "1";
      return { ...products, total: 42, items: visible ? [addedProduct, activeProduct] : [activeProduct] } as T;
    });
    vi.spyOn(api, "post").mockImplementation(async <T,>() => {
      added = true;
      return { product: addedProduct, outcome } as T;
    });
    renderConsole("/products");
    await screen.findByText(activeProduct.name);
    const search = await screen.findByPlaceholderText("输入名称或商品链接");
    fireEvent.change(search, { target: { value: "incompatible filter" } });
    fireEvent.submit(search.closest("form")!);
    await waitFor(() => expect(get).toHaveBeenCalledWith("products?q=incompatible+filter&page=1&page_size=20"), { timeout: 5000 });
    fireEvent.click(screen.getByTitle("2"));
    await waitFor(() => expect(get).toHaveBeenCalledWith("products?q=incompatible+filter&page=2&page_size=20"));

    fireEvent.click(screen.getByRole("button", { name: /添加监控商品/ }));
    fireEvent.change(screen.getByLabelText("商品 URL"), { target: { value: addedProduct.url } });
    get.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "开始监控" }));

    expect(await screen.findByText(addedProduct.name)).toBeInTheDocument();
    await waitFor(() => expect(get).toHaveBeenCalledWith("products?page=1&page_size=20"));
    expect(screen.getByPlaceholderText("输入名称或商品链接")).toHaveValue("");
    expect(screen.getByText(addedProduct.name).closest("tbody")?.querySelector("tr.ant-table-row"))
      .toContainElement(screen.getByText(addedProduct.name));
    expect(screen.queryByRole("dialog", { name: "商品详情" })).not.toBeInTheDocument();
  }, 20_000);

  it("serializes search, site, status, and pagination query parameters", () => {
    expect(productListPath({ q: "Bayou", site: "sp", status: "in_stock", page: 2, pageSize: 50 }))
      .toBe("products?q=Bayou&site=sp&status=in_stock&page=2&page_size=50");
  });

  it("shows status tags and visually marks paused rows", async () => {
    mockProducts();
    renderConsole("/products");

    expect(await screen.findByText("有货")).toBeInTheDocument();
    expect(screen.getByText("缺货")).toBeInTheDocument();
    const pausedRow = screen.getByText("Paused Product").closest("tr")!;
    expect(pausedRow).toHaveClass("products-page__row--disabled");
    expect(pausedRow).toHaveStyle({ opacity: "0.58" });
  });

  it("provides official mall links grouped by region", async () => {
    mockProducts();
    renderConsole("/products");

    fireEvent.click(await screen.findByRole("button", { name: /商城官网/ }));

    expect(await screen.findByText("美站")).toBeInTheDocument();
    expect(screen.getByText("英站")).toBeInTheDocument();
    const website = screen.getByRole("link", { name: "Smokingpipes" });
    expect(website).toHaveAttribute("href", "https://smokingpipes.com/");
    expect(website).toHaveAttribute("target", "_blank");
  }, 15_000);

  it("submits immediate checks, pauses and resumes products", async () => {
    mockProducts();
    const post = vi.spyOn(api, "post").mockResolvedValue({ queued: true });
    const patch = vi.spyOn(api, "patch").mockResolvedValue(activeProduct);
    renderConsole("/products");

    await screen.findByText("Cornell & Diehl Bayou Morning");
    const row = screen.getByText("Cornell & Diehl Bayou Morning").closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: "更多操作" }));
    fireEvent.click(await screen.findByText("立即检查"));
    await waitFor(() => expect(post).toHaveBeenCalledWith("products/1/check"));

    fireEvent.click(within(row).getByRole("button", { name: "更多操作" }));
    fireEvent.click(await screen.findByText("暂停监控"));
    await waitFor(() => expect(patch).toHaveBeenCalledWith("products/1", { enabled: false }));

    const pausedRow = screen.getByText("Paused Product").closest("tr")!;
    fireEvent.click(within(pausedRow).getByRole("button", { name: "更多操作" }));
    fireEvent.click(await screen.findByText("恢复监控"));
    await waitFor(() => expect(patch).toHaveBeenCalledWith("products/2", { enabled: true }));
  }, 15_000);

  it("requires Popconfirm confirmation before removing", async () => {
    mockProducts();
    const remove = vi.spyOn(api, "delete").mockResolvedValue(undefined);
    renderConsole("/products");

    await screen.findByText("Cornell & Diehl Bayou Morning");
    const row = screen.getByText("Cornell & Diehl Bayou Morning").closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: "移除" }));
    expect(remove).not.toHaveBeenCalled();
    await screen.findByText("确认移除该商品？");
    fireEvent.click(screen.getByRole("button", { name: "确认移除", hidden: true }));
    await waitFor(() => expect(remove).toHaveBeenCalledWith("products/1"));
  }, 15_000);

  it("shows capped recent observations in a viewport-bounded detail drawer", async () => {
    mockProducts();
    vi.spyOn(api, "post").mockResolvedValue({ product: activeProduct, outcome: "existing" });
    renderConsole("/products");

    fireEvent.click((await screen.findAllByRole("button", { name: "详情" }))[0]);
    const drawer = await screen.findByRole("dialog", { name: "商品详情" });
    expect(drawer.parentElement).toHaveStyle({ width: "min(560px, 100vw)" });
    expect(await screen.findByText("最近观察")).toBeInTheDocument();
    expect(screen.getByText("观察规格 1")).toBeInTheDocument();
    expect(screen.queryByText("观察规格 21")).not.toBeInTheDocument();
  }, 15_000);

  it("opens the existing product drawer after adding a duplicate URL", async () => {
    mockProducts();
    vi.spyOn(api, "post").mockResolvedValue({ product: activeProduct, outcome: "existing" });
    renderConsole("/products");

    fireEvent.click(await screen.findByRole("button", { name: /添加监控商品/ }));
    fireEvent.change(screen.getByLabelText("商品 URL"), { target: { value: activeProduct.url } });
    fireEvent.click(screen.getByRole("button", { name: "开始监控" }));

    expect(await screen.findByRole("dialog", { name: "商品详情" })).toBeInTheDocument();
  }, 15_000);
});
