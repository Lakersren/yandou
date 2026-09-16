import { afterEach, describe, expect, it, vi } from "vitest";

import { api, loginUrl } from "./client";

describe("api client", () => {
  it("encodes the full current console destination in the login URL", () => {
    expect(loginUrl({ pathname: "/console/products", search: "?q=香草&page=2", hash: "#details" }))
      .toBe(`/admin/login/?next=${encodeURIComponent("/console/products?q=香草&page=2#details")}`);
    expect(loginUrl({ pathname: "//other.example", search: "?unsafe=1", hash: "" }))
      .toBe("/admin/login/?next=%2Fconsole%2F");
    expect(loginUrl({ pathname: "/console-other", search: "", hash: "" }))
      .toBe("/admin/login/?next=%2Fconsole%2F");
  });

  afterEach(() => {
    document.cookie = "csrftoken=; Max-Age=0; path=/";
  });

  it("sends CSRF header on mutations", async () => {
    document.cookie = "csrftoken=test-token";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { ok: true } }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })));

    await api.post("/products", { url: "https://example.com" });

    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/api/console/v1/products"), expect.objectContaining({
      headers: expect.objectContaining({ "X-CSRFToken": "test-token" }),
    }));
  });

  it("redirects to login on 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 401 })));
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    await expect(api.get("/session")).rejects.toMatchObject({ status: 401 });
  });
});
