/**
 * build.js — Inlines external CSS and JS back into a single api/index.html
 *
 * This is required because api/dog_meta.py does server-side regex
 * manipulation on the full HTML (injecting OG meta tags, bootstrap scripts).
 * It expects a single self-contained HTML file at api/index.html.
 *
 * Usage: node build.js
 */

const fs = require('fs');
const path = require('path');

const PUBLIC = path.join(__dirname, 'public');
const OUT = path.join(__dirname, 'api', 'index.html');

let html = fs.readFileSync(path.join(PUBLIC, 'index.html'), 'utf-8');

// 1. Inline the external CSS
const cssContent = fs.readFileSync(path.join(PUBLIC, 'styles.css'), 'utf-8');
html = html.replace(
  '<link rel="stylesheet" href="styles.css">',
  `<style>\n${cssContent}\n    </style>`
);

// 2. Inline each external JS file (order matters — matches the <script> tag order)
const jsFiles = [
  'js/state.js',
  'js/analytics.js',
  'js/utils.js',
  'js/ui.js',
  'js/share.js',
  'js/dog.js',
  'js/chat.js',
  'js/preferences.js',
  'js/saved.js',
  'js/init.js',
];

for (const jsFile of jsFiles) {
  const jsContent = fs.readFileSync(path.join(PUBLIC, jsFile), 'utf-8');
  const tag = `<script src="${jsFile}"></script>`;
  html = html.replace(tag, `<script>\n${jsContent}\n    </script>`);
}

// 3. Write the inlined output
fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, html, 'utf-8');

const stats = fs.statSync(OUT);
console.log(`✅ Built api/index.html (${(stats.size / 1024).toFixed(1)} KB)`);
