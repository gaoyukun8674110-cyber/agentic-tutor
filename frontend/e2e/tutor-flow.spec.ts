import { expect, test } from '@playwright/test';

const apiBaseUrl = process.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8001';

test('login, ask tutor, and persist conversation history through the backend', async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem('ai-tutor-language', 'en');
  });

  await page.goto('/login');
  await page.getByLabel('Username').fill('test-01');
  await page.getByLabel('Password').fill('123456');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/$/);

  await page.goto('/tutor');
  await page.getByPlaceholder('Ask anything').fill('Explain Bayes rule in one sentence');
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(page.getByText('E2E mock tutor response: keep going step by step.')).toBeVisible();

  const loginResponse = await page.request.post(`${apiBaseUrl}/api/auth/login`, {
    data: { username: 'test-01', password: '123456' },
  });
  expect(loginResponse.ok()).toBeTruthy();
  const { access_token: accessToken } = await loginResponse.json();

  const historyResponse = await page.request.get(`${apiBaseUrl}/api/llm/conversations`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  expect(historyResponse.ok()).toBeTruthy();
  const history = await historyResponse.json();
  const conversationId = history.conversations[0].id;
  expect(history.conversations[0].message_count).toBe(2);

  const detailResponse = await page.request.get(
    `${apiBaseUrl}/api/llm/conversations/${conversationId}`,
    {
      headers: { Authorization: `Bearer ${accessToken}` },
    },
  );
  expect(detailResponse.ok()).toBeTruthy();
  const detail = await detailResponse.json();
  expect(detail.messages).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ role: 'user', content: 'Explain Bayes rule in one sentence' }),
      expect.objectContaining({
        role: 'assistant',
        content: 'E2E mock tutor response: keep going step by step.',
      }),
    ]),
  );
});
