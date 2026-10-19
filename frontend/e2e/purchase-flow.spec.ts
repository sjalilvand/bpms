// E2E — سناریوی §۳۵ سند از رابط کاربری: ثبت درخواست خرید، تأیید مدیر، اطلاع‌رسانی مالی، وضعیت نهایی
import { test, expect } from '@playwright/test';
import { login, logout, startPurchaseRequest } from './support';

test.describe.serial('سناریوی §۳۵ — درخواست خرید', () => {
  let iid = 0;

  test('ثبت درخواست توسط user1', async ({ page }) => {
    await login(page, 'user1');
    iid = await startPurchaseRequest(page);
    await expect(page.getByText('در جریان').first()).toBeVisible();
    // وظیفه ثبت برای شروع‌کننده ایجاد شده است
    await expect(page.getByText('ثبت درخواست خرید').first()).toBeVisible();
  });

  test('تکمیل ثبت توسط user1 (وظیفه تخصیص‌یافته)', async ({ page }) => {
    await login(page, 'user1');
    await page.goto('/inbox');
    await page.getByRole('tab', { name: 'وظایف من' }).click();
    const row = page.locator('.ant-table-row').filter({ hasText: 'ثبت درخواست خرید' }).first();
    await expect(row).toBeVisible();
    await row.getByRole('button', { name: 'انجام' }).click();
    await expect(page.locator('.ant-drawer-title')).toContainText('ثبت درخواست خرید');
    await page.getByRole('button', { name: 'ثبت', exact: true }).click();
    await expect(page.getByText('وظیفه با موفقیت تکمیل شد')).toBeVisible({ timeout: 20_000 });
  });

  test('تأیید مدیر از صف گروهی', async ({ page }) => {
    await login(page, 'manager');
    await page.goto('/inbox');
    await page.getByRole('tab', { name: 'صف گروهی' }).click();
    const row = page.locator('.ant-table-row').filter({ hasText: 'تأیید مدیر' }).first();
    await expect(row).toBeVisible();
    await row.getByRole('button', { name: 'دریافت' }).click();
    await expect(page.getByText('وظیفه دریافت شد')).toBeVisible();
    // وظیفه Claim شده به زبانه «وظایف من» منتقل می‌شود
    await page.getByRole('tab', { name: 'وظایف من' }).click();
    const myRow = page.locator('.ant-table-row').filter({ hasText: 'تأیید مدیر' }).first();
    await expect(myRow).toBeVisible();
    await myRow.getByRole('button', { name: 'انجام' }).click();
    await expect(page.locator('.ant-drawer-title')).toContainText('تأیید مدیر');
    // تصمیم: تأیید (رادیو) و دکمه نتیجه تأیید
    await page.locator('.ant-drawer .ant-radio-wrapper').filter({ hasText: 'تأیید' }).first().click();
    await page.locator('.ant-drawer').getByRole('button', { name: 'تأیید', exact: true }).click();
    await expect(page.getByText('وظیفه با موفقیت تکمیل شد')).toBeVisible({ timeout: 20_000 });
  });

  test('اطلاع‌رسانی مالی توسط finance1', async ({ page }) => {
    await login(page, 'finance1');
    await page.goto('/inbox');
    await page.getByRole('tab', { name: 'صف گروهی' }).click();
    const row = page.locator('.ant-table-row').filter({ hasText: 'اطلاع‌رسانی مالی' }).first();
    await expect(row).toBeVisible();
    await row.getByRole('button', { name: 'دریافت' }).click();
    await page.getByRole('tab', { name: 'وظایف من' }).click();
    const myRow = page.locator('.ant-table-row').filter({ hasText: 'اطلاع‌رسانی مالی' }).first();
    await expect(myRow).toBeVisible();
    await myRow.getByRole('button', { name: 'انجام' }).click();
    await expect(page.locator('.ant-drawer-title')).toContainText('اطلاع‌رسانی مالی');
    await page.locator('.ant-drawer').getByRole('button', { name: 'ثبت', exact: true }).click();
    await expect(page.getByText('وظیفه با موفقیت تکمیل شد')).toBeVisible({ timeout: 20_000 });
  });

  test('شروع‌کننده وضعیت completed را می‌بیند', async ({ page }) => {
    await login(page, 'user1');
    await page.goto('/my-requests');
    const row = page.locator('.ant-table-row').filter({ hasText: 'درخواست خرید' }).first();
    await expect(row).toBeVisible();
    await expect(row.locator('.ant-tag')).toHaveText('تکمیل‌شده', { timeout: 20_000 });
    await row.click();
    await page.waitForURL(/\/instances\/\d+/);
    await expect(page.getByText('تکمیل‌شده').first()).toBeVisible();
  });
});
