import { test, expect } from '@playwright/test';

test.describe('Authentication Flow', () => {
  test('should redirect to authentication URL', async ({ page }) => {
    // Navigate to the authentication URL from the environment configuration
    const authUrl = 'http://localhost:3004/et/dev-auth';
    
    await test.step('Navigate to authentication URL', async () => {
      await page.goto(authUrl);
    });

    await test.step('Verify page loads successfully', async () => {
      // Wait for the page to load
      await page.waitForLoadState('networkidle');
      
      // Verify we're on the correct URL
      expect(page.url()).toContain('localhost:3004');
      expect(page.url()).toContain('/et/dev-auth');
    });

    await test.step('Verify page title and content', async () => {
      // Wait for the page title to load
      await page.waitForTimeout(2000);
      
      // Check that the page has loaded (title should not be empty)
      const title = await page.title();
      expect(title).toBeTruthy();
      
      // Take a screenshot for debugging purposes
      await page.screenshot({ path: 'tests/screenshots/auth-page.png' });
    });
  });

  test('should handle navigation from main app to auth', async ({ page }) => {
    await test.step('Start from main application', async () => {
      // First go to the main application
      await page.goto('http://localhost:3001');
    });

    await test.step('Navigate to authentication', async () => {
      // Navigate to the authentication URL
      await page.goto('http://localhost:3004/et/dev-auth');
      
      // Wait for navigation to complete
      await page.waitForLoadState('networkidle');
    });

    await test.step('Verify successful redirect', async () => {
      // Verify we're on the auth page
      expect(page.url()).toContain('localhost:3004');
      expect(page.url()).toContain('/et/dev-auth');
      
      // Take a screenshot
      await page.screenshot({ path: 'tests/screenshots/auth-redirect.png' });
    });
  });
  
});
