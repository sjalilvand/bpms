// E2E — احراز هویت: ورود موفق، ورود ناموفق، خروج
import { test, expect } from '@playwright/test';
import { login, logout, PASSWORD } from './support';

test.describe('احراز هویت', () => {
  test('ورود ناموفق با گذرواژه اشتباه', async ({ page }) => {
    await page.goto('/login');
    await page.getByPlaceholder('نام کاربری').fill('admin');
    await page.getByPlaceholder('گذرواژه').fill('wrong-password');
    await page.getByRole('button', { name: 'ورود به سامانه' }).click();
    await expect(page.getByText(/نام کاربری یا گذرواژه|خطا|نامعتبر/).first()).toBeVisible({ timeout: 15_000 });
    await expect(page).toHaveURL(/login/);
  });

  test('ورود موفق مدیر سامانه و خروج', async ({ page }) => {
    await login(page, 'admin');
    await expect(page.getByText('مدیر سامانه').first()).toBeVisible();
    await logout(page);
    await expect(page.getByPlaceholder('نام کاربری')).toBeVisible();
  });

  test('بازدید مسیر محافظت‌شده بدون ورود → هدایت به لاگین', async ({ page }) => {
    await page.goto('/inbox');
    await expect(page).toHaveURL(/login/, { timeout: 15_000 });
  });
});
