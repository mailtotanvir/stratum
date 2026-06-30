import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const mainSource = readFileSync(resolve(root, 'src/main.tsx'), 'utf8');

const requiredPanels = [
  ['Runtime Console', 'console', 'RuntimeConsole'],
  ['Session Timeline', 'timeline', 'SessionTimeline'],
  ['Approvals', 'approvals', 'ApprovalQueue'],
  ['Provider Observability', 'provider', 'ProviderObservabilityPanel'],
  ['Artifacts', 'artifacts', 'ArtifactsPanel'],
  ['Settings', 'settings', 'SettingsPanel'],
];

const missing = [];

for (const [label, viewId, componentName] of requiredPanels) {
  if (!mainSource.includes(`label: '${label}'`)) {
    missing.push(`nav label: ${label}`);
  }
  if (!mainSource.includes(`id: '${viewId}'`)) {
    missing.push(`view id: ${viewId}`);
  }
  if (!mainSource.includes(`<${componentName} />`)) {
    missing.push(`component render: ${componentName}`);
  }
}

if (missing.length) {
  console.error('Desktop smoke check failed.');
  for (const item of missing) {
    console.error(`- Missing ${item}`);
  }
  process.exit(1);
}

console.log('Desktop smoke check passed.');
