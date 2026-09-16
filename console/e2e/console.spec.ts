import { expect, test, type Locator, type Page } from "@playwright/test";

const fixtureCredentials = {
  username: "operator",
  password: "operator-e2e-only",
};

export async function loginAsFixtureStaff(page: Page) {
  await page.goto("/console/");
  await expect(page).toHaveURL(/\/admin\/login/);
  await page.getByLabel(/用户名|Username/).fill(fixtureCredentials.username);
  await page.getByLabel(/密码|Password/).fill(fixtureCredentials.password);
  await page.getByRole("button", { name: /登录|Log in/ }).click();
  await expect(page).toHaveURL(/\/console\/$/);
  await expect(page.getByText("最近监控商品")).toBeVisible();
}

export function productRow(page: Page, name: string): Locator {
  return page.locator("tr").filter({ hasText: name });
}

export async function openProductActions(page: Page, name: string) {
  const row = productRow(page, name);
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "更多操作" }).click();
}

async function openProducts(page: Page) {
  await page.goto("/console/products");
  await expect(page.getByRole("button", { name: "添加监控商品" })).toBeVisible();
}

test("operator adds, pauses, checks, and removes a product", async ({ page }) => {
  await loginAsFixtureStaff(page);
  await page.getByRole("link", { name: "商品监控" }).click();
  await page.getByRole("button", { name: "添加监控商品" }).click();
  await page.getByLabel("商品 URL").fill("https://smokingpipes.com/product/test");
  await page.getByRole("button", { name: "开始监控" }).click();
  await expect(page.getByText("Test Flake")).toBeVisible();
  await openProductActions(page, "Test Flake");
  await page.getByRole("menuitem", { name: "暂停监控" }).click();
  await expect(productRow(page, "Test Flake").getByText("已暂停")).toBeVisible();
  await openProductActions(page, "Test Flake");
  await page.getByRole("menuitem", { name: "移除" }).click();
  await page.getByRole("button", { name: "确认移除" }).click();
  await expect(page.getByText("Test Flake")).not.toBeVisible();
});

test("shows an unreadable URL error without creating a product", async ({ page }) => {
  await loginAsFixtureStaff(page);
  await openProducts(page);
  await page.getByRole("button", { name: "添加监控商品" }).click();
  await page.getByLabel("商品 URL").fill("https://smokingpipes.com/product/not-readable");
  await page.getByRole("button", { name: "开始监控" }).click();
  await expect(page.getByText("暂时无法识别该商品库存")).toBeVisible();
});

test("opens the existing product drawer for a duplicate URL", async ({ page }) => {
  await loginAsFixtureStaff(page);
  await openProducts(page);
  await page.getByRole("button", { name: "添加监控商品" }).click();
  await page.getByLabel("商品 URL").fill("https://smokingpipes.com/product/seed-out-of-stock");
  await page.getByRole("button", { name: "开始监控" }).click();
  await expect(page.getByRole("dialog", { name: "商品详情" })).toBeVisible();
  await expect(page.getByRole("dialog", { name: "商品详情" }).getByRole("link", {
    name: "https://smokingpipes.com/product/seed-out-of-stock",
  })).toBeVisible();
});

test("queues retry for a seeded crawl failure", async ({ page }) => {
  await loginAsFixtureStaff(page);
  await page.goto("/console/failures");
  await expect(productRow(page, "Seed Out of Stock")).toBeVisible();
  await page.getByRole("button", { name: "重新检查" }).click();
  await expect(page.getByText("已提交重新检查")).toBeVisible();
});

test("sends a DingTalk test through the isolated sender", async ({ page }) => {
  await loginAsFixtureStaff(page);
  await page.goto("/console/dingtalk");
  await expect(page.getByText("E2E 美站群")).toBeVisible();
  await page.getByRole("button", { name: "测试发送" }).first().click();
  await page.getByRole("button", { name: /确\s*定/ }).click();
  await expect(page.getByText("测试消息已发送")).toBeVisible();
});
