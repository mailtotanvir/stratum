#!/usr/bin/env node

import { spawnSync } from 'node:child_process';

const requiredCommands = [
  {
    command: 'pkg-config',
    hint: 'Install pkg-config first. On Debian/Ubuntu: sudo apt install pkg-config',
  },
];

const requiredPkgConfigModules = [
  {
    module: 'atk',
    hint: 'Install the GTK ATK development package. On Debian/Ubuntu: sudo apt install libatk1.0-dev',
  },
  {
    module: 'gtk+-3.0',
    hint: 'Install the GTK 3 development package. On Debian/Ubuntu: sudo apt install libgtk-3-dev',
  },
  {
    module: 'gdk-3.0',
    hint: 'Install the GTK 3 development package. On Debian/Ubuntu: sudo apt install libgtk-3-dev',
  },
  {
    module: 'pango',
    hint: 'Install the Pango development package. On Debian/Ubuntu: sudo apt install libpango1.0-dev',
  },
  {
    module: 'gdk-pixbuf-2.0',
    hint: 'Install the GDK Pixbuf development package. On Debian/Ubuntu: sudo apt install libgdk-pixbuf-2.0-dev',
  },
  {
    module: 'cairo',
    hint: 'Install the Cairo development package. On Debian/Ubuntu: sudo apt install libcairo2-dev',
  },
  {
    module: 'libsoup-3.0',
    hint: 'Install the libsoup 3 development package. On Debian/Ubuntu: sudo apt install libsoup-3.0-dev',
  },
  {
    module: 'javascriptcoregtk-4.1',
    hint: 'Install the JavaScriptCore GTK development package. On Debian/Ubuntu: sudo apt install libjavascriptcoregtk-4.1-dev',
  },
  {
    module: 'webkit2gtk-4.1',
    hint: 'Install the WebKitGTK development package. On Debian/Ubuntu: sudo apt install libwebkit2gtk-4.1-dev',
  },
];

const missing = [];
const missingModules = [];

for (const { command } of requiredCommands) {
  const result = spawnSync(command, ['--version'], { stdio: 'ignore' });
  if (result.error || result.status !== 0) {
    missing.push(command);
  }
}

if (!missing.includes('pkg-config')) {
  for (const { module } of requiredPkgConfigModules) {
    const result = spawnSync('pkg-config', ['--exists', module], { stdio: 'ignore' });
    if (result.error || result.status !== 0) {
      missingModules.push(module);
    }
  }
}

if (missing.length > 0) {
  console.error('Tauri preflight failed: missing system command(s):', missing.join(', '));
  console.error('Install the missing package(s), then retry `pnpm tauri:dev`.');
  for (const { command, hint } of requiredCommands) {
    if (missing.includes(command)) {
      console.error(`- ${command}: ${hint}`);
    }
  }
  process.exit(1);
}

if (missingModules.length > 0) {
  console.error('Tauri preflight failed: missing pkg-config module(s):', missingModules.join(', '));
  console.error('Install the missing package(s), then retry `pnpm tauri:dev`.');
  for (const { module, hint } of requiredPkgConfigModules) {
    if (missingModules.includes(module)) {
      console.error(`- ${module}: ${hint}`);
    }
  }
  process.exit(1);
}
