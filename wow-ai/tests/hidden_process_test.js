'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {spawnSync} = require('node:child_process');
const path = require('node:path');

test('terminating the desktop wrapper reaps native children and grandchildren', {skip: process.platform !== 'win32'}, () => {
  const python = path.resolve(__dirname, '../../python/python.exe');
  const wrapper = path.resolve(__dirname, '../bridge/hidden-console.py');
  const result = spawnSync(python, ['-I', wrapper, python,
    path.join(__dirname, 'desktop_probe.py'), '--watch-wrapper', wrapper], {
    windowsHide: true, encoding: 'utf8', timeout: 20000,
  });
  assert.equal(result.status, 0, result.stderr || String(result.error));
  assert.match(result.stdout, /stopped the complete helper tree/);
});

test('helpers requesting new visible consoles stay off the input desktop with intact pipes', {skip: process.platform !== 'win32'}, () => {
  const python = path.resolve(__dirname, '../../python/python.exe');
  const result = spawnSync(python, ['-I', path.resolve(__dirname, '../bridge/hidden-console.py'),
    python, path.join(__dirname, 'desktop_probe.py')], {windowsHide: true, encoding: 'utf8', timeout: 15000});
  assert.equal(result.status, 0, result.stderr || String(result.error));
  assert.match(result.stdout, /isolated native child; stdin, stdout, stderr and exit status intact/);
});

test('native grandchildren inherit a hidden console instead of allocating visible windows', {skip: process.platform !== 'win32'}, () => {
  const probe = 'Add-Type -MemberDefinition \'[DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow(); [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);\' -Name ConsoleProbe -Namespace Test; $h=[Test.ConsoleProbe]::GetConsoleWindow(); $h.ToInt64(); [Test.ConsoleProbe]::IsWindowVisible($h)';
  // This inner Python process intentionally has no window-hiding code. It
  // represents the native CLI's unmodified subprocess launch (the missed case).
  const inner = `import subprocess; subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',${JSON.stringify(probe)}],check=True)`;
  const python = path.resolve(__dirname, '../../python/python.exe');
  const result = spawnSync(python, ['-I', path.resolve(__dirname, '../bridge/hidden-console.py'), python, '-c', inner], {
    windowsHide: true, encoding: 'utf8', timeout: 30000,
  });
  assert.equal(result.status, 0, result.stderr || String(result.error));
  const lines = result.stdout.trim().split(/\s+/);
  assert.ok(Number(lines[0]) > 0, 'native grandchild inherits the console');
  assert.equal(lines[1], 'False', 'inherited console is invisible');
});

test('Windows Node launchers keep nested native processes consoleless, including ESM imports', {skip: process.platform !== 'win32'}, () => {
  const preload = path.resolve(__dirname, '../bridge/hidden-child-process.js');
  const probe = 'Add-Type -MemberDefinition \'[DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();\' -Name ConsoleProbe -Namespace Test; [Test.ConsoleProbe]::GetConsoleWindow().ToInt64()';
  const code = `
    import {spawn, spawnSync} from 'node:child_process';
    const args = ['-NoProfile', '-NonInteractive', '-Command', ${JSON.stringify(probe)}];
    const sync = spawnSync('powershell.exe', args, {encoding:'utf8', windowsHide:false});
    if (sync.status !== 0) throw Error(sync.stderr);
    process.stdout.write(sync.stdout);
    const child = spawn('powershell.exe', args, {stdio:['ignore','pipe','pipe']});
    child.stdout.pipe(process.stdout);
    child.stderr.pipe(process.stderr);
    child.on('exit', code => {process.exitCode = code;});
  `;
  const result = spawnSync(process.execPath, ['--require', preload, '--input-type=module', '-e', code], {
    windowsHide: true, encoding: 'utf8', timeout: 30000,
  });
  assert.equal(result.status, 0, result.stderr || String(result.error));
  assert.deepEqual(result.stdout.trim().split(/\s+/), ['0', '0']);
});
