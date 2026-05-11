import { test, expect } from "@playwright/test";

/**
 * E2E test: open the frontend, type a sample, click Generate, wait for the
 * video to appear. The backend must already be running. In mock mode this
 * completes in < 5 seconds.
 */
test("avatar generation end-to-end", async ({ page }) => {
  await page.goto("/");

  // Heading and intro copy.
  await expect(page.getByRole("heading", { name: "AI Avatar Demo" })).toBeVisible();
  await expect(
    page.getByText(/Type a message and generate a professional avatar video/i)
  ).toBeVisible();

  // Backend health: poll until "Backend connected" or fail clearly.
  const conn = page.getByTestId("connection-status");
  await expect(conn).toContainText(/Backend connected|Backend unreachable|Checking backend/i, {
    timeout: 20_000,
  });

  // Enter sample text.
  const textarea = page.getByLabel("Message to speak");
  await textarea.fill("Hello, this is a Playwright end-to-end test of the avatar pipeline.");

  // Trigger generation.
  await page.getByTestId("generate-button").click();

  // The status banner should reflect the workflow.
  const banner = page.getByTestId("status-banner");
  await expect(banner).toBeVisible();

  // Wait for completion (mock mode is fast, real mode can take minutes).
  await expect(banner).toContainText(/Completed/i, { timeout: 5 * 60_000 });

  // Video element appears with an .mp4 src.
  const video = page.getByTestId("avatar-video");
  await expect(video).toBeVisible();
  const src = await video.getAttribute("src");
  expect(src, "video src should end with .mp4").toMatch(/\.mp4$/);

  // Download button is enabled.
  const dl = page.getByTestId("download-button");
  await expect(dl).toBeVisible();
  await expect(dl).toHaveAttribute("href", /\.mp4$/);
});
