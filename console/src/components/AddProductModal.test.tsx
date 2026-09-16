import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError, api } from "../api/client";
import type { ProductData } from "../api/types";
import { AddProductModal } from "./AddProductModal";

const product: ProductData = {
  id: 1,
  name: "Bayou Morning",
  url: "https://smokingpipes.com/p/1",
  site: { code: "sp", name: "Smokingpipes", region: "US" },
  stock_status: "in_stock",
  enabled: true,
  last_checked_at: "2026-09-14T10:00:00+08:00",
  variants: [],
};

function renderModal(props: Partial<React.ComponentProps<typeof AddProductModal>> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AddProductModal open onClose={vi.fn()} onCreated={vi.fn()} {...props} />
    </QueryClientProvider>,
  );
}

describe("AddProductModal", () => {
  it("contains exactly one editable business field", () => {
    renderModal();

    expect(screen.getAllByRole("textbox")).toHaveLength(1);
    expect(screen.getByLabelText("商品 URL")).toBeRequired();
  });

  it("keeps modal open and shows API error", async () => {
    const onClose = vi.fn();
    vi.spyOn(api, "post").mockRejectedValue(new ApiError(400, "unreadable_stock", "暂时无法识别该商品库存"));
    renderModal({ onClose });

    fireEvent.change(screen.getByLabelText("商品 URL"), { target: { value: "https://smokingpipes.com/p/1" } });
    fireEvent.click(screen.getByRole("button", { name: "开始监控" }));

    expect(await screen.findByText("暂时无法识别该商品库存")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("prevents duplicate submissions while the request is loading", async () => {
    const onClose = vi.fn();
    let resolveRequest: ((value: unknown) => void) | undefined;
    const request = new Promise((resolve) => { resolveRequest = resolve; });
    const post = vi.spyOn(api, "post").mockReturnValue(request as Promise<never>);
    renderModal({ onClose });

    fireEvent.change(screen.getByLabelText("商品 URL"), { target: { value: "https://smokingpipes.com/p/1" } });
    fireEvent.click(screen.getByRole("button", { name: "开始监控" }));

    await waitFor(() => expect(screen.getByText("开始监控").closest("button")).toBeDisabled());
    expect(post).toHaveBeenCalledTimes(1);

    resolveRequest?.({ product, outcome: "created" });
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });
});
