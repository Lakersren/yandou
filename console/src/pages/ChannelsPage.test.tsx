import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { NotificationChannelData, SessionData } from "../api/types";
import { renderConsole } from "../test/render";

const session: SessionData = { user: { id: 1, username: "operator" }, scheduler: "healthy" };
const channel: NotificationChannelData = {
  id: 7,
  platform: "feishu",
  name: "美站补货群",
  regions: ["US", "UK"],
  receive_scope_label: "美站、英站",
  enabled: true,
  webhook_configured: true,
  webhook_mask: "open.feishu.cn (...vate)",
  secret_configured: true,
};

function mockChannels() {
  return vi.spyOn(api, "get").mockImplementation(async <T,>(path: string) => (
    path === "session" ? session : [channel]
  ) as T);
}

describe("ChannelsPage", () => {
  it("does not render full channel credentials", async () => {
    mockChannels();
    renderConsole("/feishu");

    expect(await screen.findByText(/feishu\.cn/)).toBeInTheDocument();
    expect(screen.queryByText(/access_token=private/)).not.toBeInTheDocument();
    expect(screen.queryByText(/SECprivate/)).not.toBeInTheDocument();
  });

  it("keeps credentials when an edited form leaves them blank", async () => {
    mockChannels();
    const patch = vi.spyOn(api, "patch").mockResolvedValue(channel);
    renderConsole("/feishu");

    const row = (await screen.findByText("美站补货群")).closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: "编辑" }));
    expect(screen.getByText("Webhook 已配置，留空将保留现有地址。")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(patch).toHaveBeenCalledWith("notification-channels/7", {
      name: "美站补货群",
      regions: ["US", "UK"],
      enabled: true,
    }));
  });

  it("confirms and sends a channel test without credentials in the request", async () => {
    mockChannels();
    const testChannel = vi.spyOn(api, "post").mockResolvedValue({ sent: true });
    renderConsole("/feishu");

    const row = (await screen.findByText("美站补货群")).closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: "测试发送" }));
    fireEvent.click(await screen.findByRole("button", { name: /确\s*定/ }));

    await waitFor(() => expect(testChannel).toHaveBeenCalledWith("notification-channels/7/test"));
  }, 15_000);
});
