// ابزارهای مشترک E2E — ورود/خروج و انتخابگرهای فارسی
import { Page, expect } from '@playwright/test';

export const PASSWORD = 'Bpms@1234';

export async function login(page: Page, username: string, password = PASSWORD) {
  await page.goto('/login');
  await page.getByPlaceholder('نام کاربری').fill(username);
  await page.getByPlaceholder('گذرواژه').fill(password);
  await page.getByRole('button', { name: 'ورود به سامانه' }).click();
  // ورود موفق: خروج از صفحه لاگین و نمایش منوی اصلی
  await expect(page).not.toHaveURL(/login/, { timeout: 20_000 });
  await expect(page.getByRole('menuitem', { name: 'درخواست‌های من' })).toBeVisible({ timeout: 20_000 });
}

export async function logout(page: Page) {
  // ماشه منوی کاربر: span شامل آیکن کاربر و نام کامل
  await page.locator('span:has(.anticon-user)').last().click();
  await page.getByRole('menuitem', { name: 'خروج' }).click();
  await expect(page).toHaveURL(/login/, { timeout: 15_000 });
}

/** انتخاب گزینه از Select антد داخل Form.Item با برچسب مشخص */
export async function pickSelect(page: Page, label: string, optionText: string) {
  const item = page.locator('.ant-form-item').filter({ has: page.locator(`label[title="${label}"]`) });
  await item.locator('.ant-select-selector').first().click();
  await page.locator('.ant-select-dropdown:visible .ant-select-item-option').filter({ hasText: optionText }).click();
}

/** انتخاب واحد از TreeSelect */
export async function pickTreeSelect(page: Page, label: string, nodeText: string) {
  const item = page.locator('.ant-form-item').filter({ has: page.locator(`label[title="${label}"]`) });
  await item.locator('.ant-select-selector').first().click();
  await page.locator('.ant-select-tree-treenode:visible').filter({ hasText: nodeText }).first().click();
}

/** انتخاب تاریخ جلالی از طریق پنل تقویم (کلیک روی سلول امروز) */
export async function pickJalaliToday(page: Page, label: string) {
  const item = page.locator('.ant-form-item').filter({ has: page.locator(`label[title="${label}"]`) });
  await item.locator('[data-testid="jalali-datepicker"] input').click();
  // سلول امروز در پنل rmdp کلاس rmdp-today دارد
  const todayCell = page.locator('.rmdp-day.rmdp-today:not(.rmdp-disabled)').first();
  await expect(todayCell).toBeVisible({ timeout: 10_000 });
  await todayCell.click();
  // بستن پنل با کلیک بیرون
  await page.locator('.ant-drawer-title, .ant-modal-title').first().click();
}
