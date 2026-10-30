// Real browser + loopback SMTP acceptance. Uses only a fresh isolated data directory.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const { spawn } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const { chromium } = require(path.join(root, 'frontend/node_modules/playwright'));
const output = path.resolve(process.argv[2] || path.join(root, '.ui_validation', `auth-${Date.now()}`));
assert(output.startsWith(path.join(root, '.ui_validation') + path.sep));
assert(!fs.existsSync(output), 'Choose a fresh acceptance directory');
const base = 'http://127.0.0.1:15261';
const api = 'http://127.0.0.1:18061';
const children = [], messages = [], report = { checks: [], screenshots: [], pageErrors: [] };
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
fs.mkdirSync(output, { recursive: true });

function start(binary, args, cwd, env) {
  const child = spawn(binary, args, { cwd, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  children.push(child);
  for (const stream of [child.stdout, child.stderr]) stream.on('data', chunk => fs.appendFileSync(path.join(output, 'servers.log'), chunk));
  return child;
}

// Never forwards mail. Messages remain in process memory and are not written to logs.
const smtp = net.createServer(socket => {
  socket.setEncoding('utf8');
  let buffer = '', data = false, message = [];
  socket.write('220 localhost acceptance SMTP\r\n');
  socket.on('error', () => {});
  socket.on('data', chunk => {
    buffer += chunk;
    while (buffer.includes('\n')) {
      const index = buffer.indexOf('\n'), line = buffer.slice(0, index).replace(/\r$/, '');
      buffer = buffer.slice(index + 1);
      if (data) {
        if (line === '.') { messages.push(message.join('\n')); message = []; data = false; socket.write('250 Accepted locally\r\n'); }
        else message.push(line.replace(/^\.\./, '.'));
      } else if (/^(EHLO|HELO)/i.test(line)) socket.write('250 localhost\r\n');
      else if (/^DATA/i.test(line)) { data = true; socket.write('354 End with dot\r\n'); }
      else if (/^QUIT/i.test(line)) socket.end('221 Bye\r\n');
      else socket.write('250 OK\r\n');
    }
  });
});

async function mailLink(after, kind) {
  for (let attempt = 0; attempt < 80; attempt++) {
    for (const raw of messages.slice(after)) {
      const decoded = /Content-Transfer-Encoding: base64/i.test(raw)
        ? Buffer.from(raw.slice(raw.indexOf('\n\n') + 2).replace(/\s/g, ''), 'base64').toString('utf8')
        : raw.replace(/=\n/g, '').replace(/=([0-9A-F]{2})/gi, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
      const match = decoded.match(/http:\/\/127\.0\.0\.1:15261\/#[^\s<>]+/);
      if (match && match[0].includes(`auth=${kind}`)) return match[0];
    }
    await pause(100);
  }
  throw new Error(`No ${kind} email delivered to local SMTP`);
}

async function run() {
  let browser, page;
  await new Promise(resolve => smtp.listen(0, '127.0.0.1', resolve));
  try {
    const env = { ...process.env, ATLAS_ENV_FILE: '', DATA_DIR: path.join(output, 'data'), ACCESS_MODE: 'multiuser',
      OFFLINE_MODE: 'false', REGISTRATION_ENABLED: 'true', SESSION_SECURE_COOKIE: 'false',
      RESEARCH_MODEL_ENABLED: 'false', DASHSCOPE_API_KEY: '', TUTOR_DEFAULT_API_KEY: '', NEO4J_URI: 'bolt://127.0.0.1:1', GROBID_BASE_URL: 'http://127.0.0.1:1',
      SMTP_HOST: '127.0.0.1', SMTP_PORT: String(smtp.address().port), SMTP_SECURITY: 'plain', SMTP_USERNAME: '', SMTP_PASSWORD: '',
      SMTP_FROM_EMAIL: 'paperstride@example.test', AUTH_PUBLIC_URL: base };
    const python = process.env.ATLAS_PYTHON || path.join(root, 'backend/.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
    start(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '18061'], path.join(root, 'backend'), env);
    start(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '15261', '--strictPort'], path.join(root, 'frontend'), { ...process.env, ATLAS_API_TARGET: api });
    let ready = false;
    for (let attempt = 0; attempt < 100; attempt++) {
      try { const result = await fetch(`${base}/api/auth/session`); if (result.ok && (await result.json()).recovery_email_enabled) { ready = true; break; } } catch {}
      await pause(200);
    }
    assert(ready, 'Isolated API and SMTP capability must become ready');
    browser = await chromium.launch({ headless: true, ...(process.env.ATLAS_CHROME_PATH ? { executablePath: process.env.ATLAS_CHROME_PATH } : process.platform === 'win32' ? { executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' } : {}) });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
    page = await context.newPage();
    page.setDefaultTimeout(15000);
    page.on('pageerror', error => report.pageErrors.push(error.message));
    await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
    const shot = async name => {
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.waitForTimeout(150);
      await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
      report.screenshots.push(`${name}.png`);
      const widths = await page.evaluate(() => ({ viewport: innerWidth, content: document.documentElement.scrollWidth }));
      assert(widths.content <= widths.viewport + 1, `${name}: horizontal overflow`);
    };
    await page.goto(base);
    await page.getByRole('heading', { name: /登录/ }).waitFor();
    await shot('login-desktop');
    await page.setViewportSize({ width: 390, height: 844 });
    await shot('login-mobile');
    await page.setViewportSize({ width: 1440, height: 1000 });
    const username = 'browser-reader', email = 'browser-reader@example.test';
    const firstPassword = 'research notebook password';
    const secondPassword = 'updated research password';
    const thirdPassword = 'recovered research password';
    const submit = name => page.getByRole('button', { name, exact: true }).click();
    const signedIn = () => page.getByRole('heading', { name: '研究工作台', exact: true }).waitFor();
    const authPost = async (url, data) => {
      const session = await (await context.request.get(`${base}/api/auth/session`)).json();
      return context.request.post(`${base}/api/auth/${url}`, { data, headers: session.csrf_token ? { 'X-Atlas-CSRF': session.csrf_token } : {} });
    };
    await submit('创建新账号');
    await page.getByLabel('用户名', { exact: true }).fill(username);
    await page.getByLabel('邮箱（选填）', { exact: true }).fill(email);
    await page.getByLabel('密码', { exact: true }).fill(firstPassword);
    await page.getByLabel('确认密码', { exact: true }).fill('does not match');
    await submit('注册并进入');
    await page.getByText('两次输入的密码不一致', { exact: true }).waitFor();
    assert.equal(messages.length, 0, 'Invalid registration must not send mail');
    await page.getByLabel('确认密码', { exact: true }).fill(firstPassword);
    await submit('注册并进入');
    await signedIn();
    const verificationLink = await mailLink(0, 'verify-email');
    await page.goto(verificationLink);
    await page.getByRole('heading', { name: '验证邮箱', exact: true }).waitFor();
    assert(!page.url().includes('token='), 'Bearer token must leave the address bar');
    await submit('验证邮箱');
    await page.getByText(/邮箱验证成功|邮箱已验证/).waitFor();
    const verifiedSession = await (await context.request.get(`${base}/api/auth/session`)).json();
    assert.equal(verifiedSession.user.email, email);
    await submit(/返回工作空间/);
    await signedIn();
    await shot('registered-workspace');
    assert.equal((await authPost('logout')).status(), 200);
    await page.goto(base);
    await page.getByLabel('用户名或邮箱', { exact: true }).fill(email);
    await page.getByLabel('密码', { exact: true }).fill(firstPassword);
    await submit(/^登\s*录$/);
    await signedIn();
    report.checks.push('registration-confirmation-email-delivery-verification-email-login');

    // Independent browser cookie jars must never expose another account's data.
    const ownerSession = await (await context.request.get(`${base}/api/auth/session`)).json();
    const createdProject = await context.request.post(`${base}/api/projects`, {
      data: {title: 'Private synthetic browser research', research_question: 'Only tests account isolation',
        domain: 'robot_policy_learning', constraints: {version: 1, objective: 'Verify isolation'}},
      headers: {'X-Atlas-CSRF': ownerSession.csrf_token},
    });
    assert.equal(createdProject.status(), 201);
    const privateProject = await createdProject.json();
    const stranger = await browser.newContext();
    assert.equal((await stranger.request.post(`${base}/api/auth/register`, {data: {
      username: 'isolated-browser-reader', password: 'another synthetic long password',
    }})).status(), 201);
    assert.equal((await stranger.request.get(`${base}/api/projects/${privateProject.id}`)).status(), 404);
    const strangerProjects = await (await stranger.request.get(`${base}/api/projects`)).json();
    assert(Array.isArray(strangerProjects.items));
    assert(!strangerProjects.items.some(item => item.id === privateProject.id));
    await stranger.close();
    report.checks.push('independent-browser-accounts-cannot-read-another-research-space');

    // Keep a second live session to prove reset revokes all devices.
    const other = await browser.newContext();
    assert.equal((await other.request.post(`${base}/api/auth/login`, { data: { username, password: firstPassword } })).status(), 200);
    assert.equal((await authPost('logout')).status(), 200);
    await page.goto(base);
    await submit('忘记密码？');
    await page.getByLabel('已验证的邮箱', { exact: true }).fill(email);
    const beforeReset = messages.length;
    await submit('发送重置邮件');
    await mailLink(beforeReset, 'reset-password');
    await shot('forgot-password-sent');
    const knownResponse = await (await context.request.post(`${base}/api/auth/forgot-password`, { data: { email } })).json();
    const unknownResponse = await (await context.request.post(`${base}/api/auth/forgot-password`, { data: { email: 'missing@example.test' } })).json();
    assert.deepEqual(knownResponse, unknownResponse, 'Email existence must not leak in responses');
    // Use the newest link because requesting another intentionally invalidates the prior link.
    const newestReset = await mailLink(beforeReset + 1, 'reset-password');
    await page.goto(newestReset);
    await page.getByRole('heading', { name: '设置新密码', exact: true }).waitFor();
    assert(!page.url().includes('token='));
    await page.getByLabel('新密码', { exact: true }).fill(secondPassword);
    await page.getByLabel('确认新密码', { exact: true }).fill(secondPassword);
    await submit('保存新密码');
    await page.getByText(/密码已更新|密码已修改/).waitFor();
    assert.equal((await (await other.request.get(`${base}/api/auth/session`)).json()).user, null);
    assert.equal((await context.request.post(`${base}/api/auth/login`, { data: { username, password: firstPassword } })).status(), 401);
    const usedToken = new URLSearchParams(new URL(newestReset).hash.slice(1)).get('token');
    assert.equal((await context.request.post(`${base}/api/auth/reset-password`, { data: { token: usedToken, new_password: thirdPassword } })).status(), 400);
    await page.getByLabel('用户名或邮箱', { exact: true }).fill(email);
    await page.getByLabel('密码', { exact: true }).fill(secondPassword);
    await submit(/^登\s*录$/);
    await signedIn();
    report.checks.push('email-reset-single-use-revokes-all-sessions-and-old-password');
    await other.close();

    await page.goto(`${base}/settings?tab=account`);
    await page.getByRole('heading', { name: '账号与安全', exact: true }).waitFor();
    await shot('account-security-desktop');
    await page.setViewportSize({ width: 390, height: 844 });
    await shot('account-security-mobile');
    await page.setViewportSize({ width: 1440, height: 1000 });
    const additional = await browser.newContext();
    assert.equal((await additional.request.post(`${base}/api/auth/login`, { data: { username, password: secondPassword } })).status(), 200);
    await submit(/刷新会话/);
    await page.getByRole('button', { name: '退出其他会话', exact: true }).click();
    await page.getByText(/其他登录会话已退出，当前会话已保留/).waitFor();
    assert.equal((await (await additional.request.get(`${base}/api/auth/session`)).json()).user, null);
    await additional.close();
    await page.getByRole('button', { name: '切换到深色主题' }).click();
    await shot('account-security-dark');
    await page.getByRole('button', { name: '切换到浅色主题' }).click();
    await page.getByLabel('生成恢复码的当前密码', { exact: true }).fill(secondPassword);
    await submit('生成新恢复码');
    await page.getByText('恢复码仅显示本次', { exact: true }).waitFor();
    const code = await page.locator('.atlas-recovery-code').innerText();
    assert(code.length > 30);
    report.checks.push('security-settings-issue-code-and-revoke-other-sessions');
    assert.equal((await authPost('logout')).status(), 200);
    await page.goto(base);
    await submit('忘记密码？');
    await submit('使用一次性恢复码');
    await page.getByLabel('账号用户名', { exact: true }).fill(username);
    await page.getByLabel('一次性恢复码', { exact: true }).fill(code);
    await page.getByLabel('新密码', { exact: true }).fill(thirdPassword);
    await page.getByLabel('确认新密码', { exact: true }).fill(thirdPassword);
    await submit('重设密码');
    await page.getByText(/密码已更新|密码已修改/).waitFor();
    assert.equal((await context.request.post(`${base}/api/auth/recover`, { data: { username, code, new_password: firstPassword } })).status(), 401);
    await page.getByLabel('用户名或邮箱', { exact: true }).fill(username);
    await page.getByLabel('密码', { exact: true }).fill(thirdPassword);
    await submit(/^登\s*录$/);
    await signedIn();
    report.checks.push('recovery-code-reset-and-single-use');
    await page.getByRole('button', { name: '切换到深色主题' }).click();
    await shot('workspace-dark');
    report.checks.push('desktop-mobile-dark-no-horizontal-overflow');
    assert.equal(report.pageErrors.length, 0);
    report.passed = true;
  } catch (error) {
    report.passed = false; report.error = error.message; report.receivedEmails = messages.length; process.exitCode = 1;
    if (page) await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true }).catch(() => {});
  } finally {
    if (browser) await browser.close();
    for (const child of children.reverse()) {
      if (child.exitCode === null) {
        const stopped = new Promise(resolve => child.once('exit', resolve));
        child.kill(); await Promise.race([stopped, pause(2000)]);
      }
    }
    await new Promise(resolve => smtp.close(resolve));
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify({ output, ...report }, null, 2));
  }
}
run().catch(error => { console.error(error.message); process.exitCode = 1; });
