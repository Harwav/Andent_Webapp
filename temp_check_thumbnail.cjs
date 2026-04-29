const { chromium } = require('@playwright/test');

(async () => {
    const browser = await chromium.launch();
    const page = await browser.newPage();

    const errors = [];
    page.on('console', msg => {
        if (msg.type() === 'error') {
            errors.push(msg.text());
        }
    });
    page.on('pageerror', err => {
        errors.push(err.message);
    });

    try {
        await page.goto('http://localhost:8090/static/temp_thumbnail_comparison.html', { waitUntil: 'networkidle', timeout: 15000 });

        // Wait for thumbnails to render
        await page.waitForTimeout(5000);

        // Check if SVG rendered
        const svgBox = await page.$('#svg-box svg');
        console.log('SVG rendered:', svgBox ? 'YES' : 'NO');

        // Check if PNG rendered
        const pngStatus = await page.$('#png-status img');
        console.log('PNG rendered:', pngStatus ? 'YES' : 'NO');

        // Check for any errors
        if (errors.length > 0) {
            console.log('ERRORS:', errors);
        } else {
            console.log('No console errors');
        }

        // Take a quick screenshot for verification
        await page.screenshot({ path: 'temp_thumb_check.png' });
        console.log('Screenshot saved to temp_thumb_check.png');

    } catch (e) {
        console.error('Page load error:', e.message);
    }

    await browser.close();
})();