import { expect, test } from '@playwright/test';

async function asRole(page, role) {
  await page.addInitScript((selectedRole) => {
    localStorage.setItem('userInfo', JSON.stringify({
      id: `${selectedRole.toLowerCase()}-id`,
      firebase_uid: `${selectedRole.toLowerCase()}-uid`,
      email: `${selectedRole.toLowerCase()}@example.edu`,
      role: selectedRole,
      permissions: [],
      is_active: true,
    }));
  }, role);
}

test('teacher reaches generation but not reviewer or Moodle admin', async ({ page }) => {
  await asRole(page, 'Teacher');
  await page.goto('/sinh-cau-hoi');
  await expect(page).toHaveURL(/sinh-cau-hoi/);
  await page.goto('/kiem-duyet');
  await expect(page).toHaveURL(/trang-chu/);
  await page.goto('/quan-ly-moodle');
  await expect(page).toHaveURL(/trang-chu/);
});

test('reviewer reaches review queue but not teacher generation', async ({ page }) => {
  await asRole(page, 'Reviewer');
  await page.goto('/kiem-duyet');
  await expect(page).toHaveURL(/kiem-duyet/);
  await page.goto('/sinh-cau-hoi');
  await expect(page).toHaveURL(/trang-chu/);
});

test('admin reaches Moodle operations and is blocked from teacher-only generation', async ({ page }) => {
  await asRole(page, 'Admin');
  await page.goto('/quan-ly-moodle');
  await expect(page.getByRole('heading', { name: 'Moodle target' })).toBeVisible();
  await page.goto('/sinh-cau-hoi');
  await expect(page).toHaveURL(/trang-chu/);
});
