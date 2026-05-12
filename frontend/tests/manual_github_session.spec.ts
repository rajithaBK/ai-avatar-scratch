import { test } from "@playwright/test";

/**
 * Opens a real browser so you can sign in to GitHub and use the website manually.
 *
 * Run from `frontend/`:
 *   npm run test:github-browser
 *
 * Flow:
 * 1. Chromium opens on GitHub login — sign in (2FA, SSO, etc.) in the window.
 * 2. Playwright Inspector opens — click **Resume** (▶) when you are done on that page.
 * 3. Browser navigates to your repo — verify files, sync settings, whatever you need.
 * 4. Click **Resume** again to finish the test.
 *
 * Override repo with: `set GITHUB_REPO=owner/name` (Windows) or `GITHUB_REPO=owner/name npm run ...`
 */
test.use({
  headless: false,
  viewport: { width: 1280, height: 900 },
});

const REPO = process.env.GITHUB_REPO || "rajithaBK/ai-avatar-scratch";

test.describe("Manual GitHub session", () => {
  test("login page, then repository (pause for your authentication)", async ({ page }) => {
    test.setTimeout(0);

    await page.goto("https://github.com/login");
    // Pause so you can complete login / 2FA. Inspector: click Resume when ready.
    await page.pause();

    await page.goto(`https://github.com/${REPO}`);
    await page.pause();
  });
});
