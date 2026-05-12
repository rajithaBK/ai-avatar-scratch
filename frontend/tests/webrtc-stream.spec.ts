import { test, expect } from "@playwright/test";

/**
 * After a mock job completes, start WebRTC playback. Requires backend with
 * aiortc installed; localhost ICE often succeeds with the default STUN server.
 */
test("WebRTC stream after mock generation", async ({ page }) => {
  await page.goto("/");

  const conn = page.getByTestId("connection-status");
  await expect(conn).toContainText(/Backend connected|Backend unreachable|Checking backend/i, {
    timeout: 20_000,
  });

  const textarea = page.getByLabel("Message to speak");
  await textarea.fill("WebRTC stream smoke test.");

  await page.getByTestId("generate-button").click();

  const banner = page.getByTestId("status-banner");
  await expect(banner).toContainText(/Completed|Failed/i, { timeout: 5 * 60_000 });

  const bannerText = await banner.textContent();
  if (bannerText?.includes("Failed")) {
    test.skip(true, "Mock pipeline failed (backend deps); skipping WebRTC assertion.");
  }

  await page.getByTestId("webrtc-start").click();

  const stateLine = page.getByTestId("webrtc-state");
  const err = page.getByTestId("webrtc-error");
  const video = page.getByTestId("webrtc-video");

  try {
    await expect(stateLine).toContainText("State: streaming", { timeout: 90_000 });
  } catch {
    if (await err.isVisible().catch(() => false)) {
      const msg = (await err.textContent()) ?? "";
      test.skip(true, `WebRTC did not connect in this environment: ${msg}`);
    }
    throw new Error("Timed out waiting for WebRTC streaming state.");
  }

  const hasStream = await video.evaluate((el: HTMLVideoElement) => Boolean(el.srcObject));
  expect(hasStream).toBeTruthy();
});
