// E2E — شرط‌ساز بصری روی نمودار BPMN (فاز ۴): بازکردن شرط موجود، ساخت شرط جدید، ذخیره و اعتبارسنجی
import { test, expect, Page } from '@playwright/test';
import { login } from './support';

async function openDesigner(page: Page) {
  await page.goto('/processes');
  const row = page.locator('.ant-table-row').filter({ hasText: 'درخواست خرید' }).first();
  await expect(row).toBeVisible();
  await row.getByRole('button', { name: 'طراحی' }).click();
  await page.waitForURL(/\/processes\/\d+\/design/, { timeout: 20_000 });
  await expect(page.getByText('تنظیمات فعالیت انتخابی')).toBeVisible({ timeout: 20_000 });
}

/** انتخاب عنصر نمودار از طریق رجیستری bpmn-js (اتکاپذیرتر از کلیک مختصاتی روی خط) */
async function selectFlow(page: Page, flowId: string) {
  await page.waitForFunction((id) => {
    const m = (window as any).__bpms_modeler;
    return !!(m && m.get('elementRegistry').get(id));
  }, flowId, { timeout: 20_000 });
  await page.evaluate((id) => {
    const m = (window as any).__bpms_modeler;
    const el = m.get('elementRegistry').get(id);
    m.get('selection').select(el);
  }, flowId);
}

test.describe.serial('شرط‌ساز بصری روی BPMN', () => {
  test('نمایش شرط موجود جریان تأیید در شرط‌ساز', async ({ page }) => {
    await login(page, 'designer');
    await openDesigner(page);
    await selectFlow(page, 'Flow_Approve');
    await expect(page.getByTestId('condition-section')).toBeVisible();
    await expect(page.getByTestId('cond-preview')).toContainText("action == 'approve'");
    await expect(page.getByText('شرط تعریف‌شده')).toBeVisible();
  });

  test('ساخت شرط جدید بصری روی جریان «رد» و اعمال روی مدل', async ({ page }) => {
    await login(page, 'designer');
    await openDesigner(page);
    await selectFlow(page, 'Flow_Reject');
    await expect(page.getByTestId('condition-section')).toBeVisible();
    const section = page.getByTestId('condition-section');
    await section.getByRole('combobox').first().fill('action');
    // انتخاب پیشنهاد «action» برای بستن دراپ‌داون AutoComplete
    await page.locator('.ant-select-dropdown:visible .ant-select-item-option').filter({ hasText: /^action$/ }).first().click();
    // دومین select در ردیف، انتخابگر عملگر است (اولی AutoComplete فیلد)
    await section.locator('.ant-select').nth(1).click();
    await page.locator('.ant-select-dropdown:visible .ant-select-item-option').filter({ hasText: 'برابر است با' }).first().click();
    await section.getByPlaceholder('مقدار (عدد، متن، true/false)').first().fill('reject');
    await expect(page.getByTestId('cond-preview')).toContainText("action == 'reject'");
    await page.getByTestId('apply-condition').click();
    await expect(page.getByText('شرط مسیر اعمال شد')).toBeVisible();
  });

  test('ایجاد نسخه جدید، ذخیره پیش‌نویس و اعتبارسنجی بدون خطا', async ({ page }) => {
    await login(page, 'designer');
    await openDesigner(page);
    await page.getByRole('button', { name: 'نسخه جدید از این مدل' }).click();
    await page.getByRole('button', { name: 'ایجاد' }).click();
    await expect(page.getByText('نسخه پیش‌نویس جدید ساخته شد')).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText('پیش‌نویس').first()).toBeVisible();
    await page.getByRole('button', { name: 'ذخیره پیش‌نویس' }).click();
    await expect(page.getByText('پیش‌نویس ذخیره شد')).toBeVisible({ timeout: 20_000 });
    await page.getByRole('button', { name: 'اعتبارسنجی' }).click();
    await page.waitForTimeout(1500);
    await expect(page.getByText('خطاهای قطعی')).toHaveCount(0);
  });

  test('جریان غیرشرطی — دروازه موازی شرط نمی‌پذیرد', async ({ page }) => {
    await login(page, 'designer');
    await openDesigner(page);
    await selectFlow(page, 'Flow_Split_Order');
    await expect(page.getByText('شرط فقط روی جریان‌های خروجی از دروازه انحصاری/فراگیر اعمال می‌شود')).toBeVisible();
  });
});
