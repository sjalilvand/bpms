// E2E — گزارش‌ساز و KPI (فاز ۷)
// شاخص‌ها، نمودارهای تعاملی ECharts، فیلترها، برگه‌ها،
// ذخیره/اجرا/حذف گزارش و دانلود خروجی Excel و PDF
import fs from 'node:fs';
import { test, expect } from '@playwright/test';
import { login, logout, startPurchaseRequest } from './support';

const REPORT_NAME = `گزارش آزمون E2E — ${Date.now()}`;

test.describe('گزارش‌ساز و KPI', () => {

  test('نمایش شاخص‌ها، نمودارهای تعاملی و برگه‌ها', async ({ page }) => {
    // تولید داده: ثبت یک درخواست خرید (نمونه در جریان + وظایف فعال)
    await login(page, 'user1');
    await startPurchaseRequest(page);
    await logout(page);

    await login(page, 'admin');
    await page.getByRole('menuitem', { name: /گزارش‌ساز/ }).click();
    await expect(page).toHaveURL(/reports/);

    // کارت‌های KPI — با داده واقعی
    await expect(page.getByText('مجموع نمونه‌ها').first()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText('نرخ تکمیل').first()).toBeVisible();
    await expect(page.getByText('میانگین چرخه').first()).toBeVisible();

    // نمودار حجم روزانه (رندر روی canvas)
    const volume = page.getByTestId('volume-chart');
    await expect(volume).toBeVisible({ timeout: 20_000 });
    await expect(volume.locator('canvas')).toBeVisible();

    // دونات وضعیت — نمونه در جریان وجود دارد → canvas
    const donut = page.getByTestId('status-donut');
    await expect(donut.locator('canvas')).toBeVisible({ timeout: 15_000 });

    // تعامل: hover روی نمودار حجم
    await volume.locator('canvas').hover({ position: { x: 200, y: 120 } });

    // فیلتر بازه: تغییر به ۷ روز اخیر و اطمینان از بارگذاری دوباره
    await page.locator('.ant-select-selector').filter({ hasText: '۳۰ روز اخیر' }).first().click();
    await page.locator('.ant-select-dropdown:visible .ant-select-item-option')
      .filter({ hasText: '۷ روز اخیر' }).click();
    await expect(page.locator('.ant-select-selector').filter({ hasText: '۷ روز اخیر' }).first()).toBeVisible();
    await expect(page.getByText('مجموع نمونه‌ها').first()).toBeVisible();

    // برگه گلوگاه‌ها: نمودار میله‌ای افقی + جدول
    await page.getByRole('tab', { name: /گلوگاه‌های فرایند/ }).click();
    const bn = page.getByTestId('bottleneck-chart');
    await expect(bn.locator('canvas')).toBeVisible({ timeout: 15_000 });

    // برگه بار کاری: نمودار انباشته + جدول
    await page.getByRole('tab', { name: /بار کاری افراد و صف‌ها/ }).click();
    const wl = page.getByTestId('workload-chart');
    await expect(wl.locator('canvas')).toBeVisible({ timeout: 15_000 });

    await logout(page);
  });

  test('ذخیره پیکربندی، اجرا و حذف گزارش ذخیره‌شده', async ({ page }) => {
    await login(page, 'admin');
    await page.goto('/reports');
    await expect(page.getByText('مجموع نمونه‌ها').first()).toBeVisible({ timeout: 20_000 });

    // ذخیره پیکربندی فعلی
    await page.getByRole('button', { name: 'ذخیره پیکربندی' }).click();
    const modal = page.locator('.ant-modal').filter({ hasText: 'ذخیره پیکربندی فعلی گزارش' });
    await modal.getByPlaceholder('نام گزارش').fill(REPORT_NAME);
    await modal.getByPlaceholder('توضیح (اختیاری)').fill('ساخته‌شده توسط آزمون E2E فاز ۷');
    await modal.getByRole('button', { name: 'ذخیره' }).click();
    await expect(page.getByText('گزارش ذخیره شد')).toBeVisible();

    // ردیف گزارش در جدول گزارش‌های ذخیره‌شده
    const row = page.locator('.ant-table-row').filter({ hasText: REPORT_NAME });
    await expect(row).toBeVisible({ timeout: 10_000 });

    // اجرای گزارش ذخیره‌شده
    await row.getByRole('button', { name: 'اجرا' }).click();
    await expect(page.getByText(/مجموع نمونه‌ها|نرخ تکمیل|ردیف/).first()).toBeVisible({ timeout: 10_000 });

    // حذف گزارش (پاکسازی)
    await row.getByRole('button', { name: 'حذف' }).click();
    await page.locator('.ant-modal-confirm').getByRole('button', { name: 'حذف' }).click();
    await expect(page.getByText('حذف شد')).toBeVisible();
    await expect(page.locator('.ant-table-row').filter({ hasText: REPORT_NAME })).toHaveCount(0);

    await logout(page);
  });

  test('دانلود خروجی Excel و PDF', async ({ page }) => {
    await login(page, 'admin');
    await page.goto('/reports');
    await expect(page.getByText('مجموع نمونه‌ها').first()).toBeVisible({ timeout: 20_000 });

    // Excel — کتاب‌کار xlsx
    const [xl] = await Promise.all([
      page.waitForEvent('download', { timeout: 30_000 }),
      page.getByTestId('export-excel').click(),
    ]);
    expect(xl.suggestedFilename()).toMatch(/\.xlsx$/);
    const xlPath = await xl.path();
    const xlStat = fs.statSync(xlPath);
    expect(xlStat.size).toBeGreaterThan(2000);
    // امضای ZIP/OOXML
    const fd = fs.openSync(xlPath, 'r');
    const buf = Buffer.alloc(2);
    fs.readSync(fd, buf, 0, 2, 0);
    fs.closeSync(fd);
    expect(buf.toString('ascii')).toBe('PK');

    // PDF — سند فارسی
    const [pdf] = await Promise.all([
      page.waitForEvent('download', { timeout: 60_000 }),
      page.getByTestId('export-pdf').click(),
    ]);
    expect(pdf.suggestedFilename()).toMatch(/\.pdf$/);
    const pdfPath = await pdf.path();
    const pdfStat = fs.statSync(pdfPath);
    expect(pdfStat.size).toBeGreaterThan(5000);
    const pfd = fs.openSync(pdfPath, 'r');
    const pbuf = Buffer.alloc(5);
    fs.readSync(pfd, pbuf, 0, 5, 0);
    fs.closeSync(pfd);
    expect(pbuf.toString('ascii')).toBe('%PDF-');

    await logout(page);
  });

});
