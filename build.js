/**
 * build.js — Compiles the Expo Web app and deploys static assets.
 *
 * It runs `npx expo export` in the frontend directory, copies the output to
 * the root `public` directory, and copies `dist/index.html` to `api/index.html`
 * so the dynamic server-side regex manipulation in api/dog_meta.py continues
 * to work seamlessly.
 *
 * Usage: node build.js
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

try {
  console.log('📦 Running Expo Web static export inside /frontend...');
  execSync('npx expo export', {
    cwd: path.join(__dirname, 'frontend'),
    stdio: 'inherit',
  });

  const distDir = path.join(__dirname, 'frontend', 'dist');
  const publicDir = path.join(__dirname, 'public');
  const apiIndex = path.join(__dirname, 'api', 'index.html');

  if (!fs.existsSync(distDir)) {
    throw new Error(`Export directory not found at ${distDir}`);
  }

  console.log('🔄 Copying Expo build assets to public/...');

  // Helper to recursively copy directories
  function copyRecursiveSync(src, dest) {
    const exists = fs.existsSync(src);
    const stats = exists && fs.statSync(src);
    const isDirectory = exists && stats.isDirectory();
    if (isDirectory) {
      if (!fs.existsSync(dest)) {
        fs.mkdirSync(dest, { recursive: true });
      }
      fs.readdirSync(src).forEach((childItemName) => {
        copyRecursiveSync(path.join(src, childItemName), path.join(dest, childItemName));
      });
    } else {
      fs.copyFileSync(src, dest);
    }
  }

  // Copy dist/ to public/
  copyRecursiveSync(distDir, publicDir);

  // Copy dist/index.html to api/index.html for Serverless Function compatibility
  fs.mkdirSync(path.dirname(apiIndex), { recursive: true });
  fs.copyFileSync(path.join(distDir, 'index.html'), apiIndex);

  console.log('✅ Build completed successfully! Frontends merged.');
} catch (error) {
  console.error('❌ Build failed:', error);
  process.exit(1);
}
