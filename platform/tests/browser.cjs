const { chromium } = require("../frontend/node_modules/@playwright/test");
const path = require("path");
(async () => {
  const chrome =
    process.env.CHROME_PATH ||
    (require("fs").existsSync(
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    )
      ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
      : undefined);
  const browser = await chromium.launch({
    headless: true,
    ...(chrome ? { executablePath: chrome } : {}),
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1080 },
    deviceScaleFactor: 1,
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("http://127.0.0.1:9080");
  await page.getByRole("heading", { name: "欢迎回到工作台" }).waitFor();
  await page.waitForTimeout(400);
  await page.screenshot({
    animations: "disabled",
    path: path.resolve("screenshots/login.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "进入工作台" }).click();
  await page.getByRole("heading", { name: "你好，研究员." }).waitFor();
  await page.waitForTimeout(400);
  await page.screenshot({
    animations: "disabled",
    path: path.resolve("screenshots/overview.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: /知识库/ })
    .first()
    .click();
  await page.getByRole("heading", { name: "你的知识，井然有序。" }).waitFor();
  await page.waitForTimeout(400);
  await page.screenshot({
    animations: "disabled",
    path: path.resolve("screenshots/documents.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "评测中心", exact: true }).click();
  await page.getByRole("heading", { name: "衡量每一次进步。" }).waitFor();
  await page
    .getByRole("button", { name: /Is 3M a capital/ })
    .first()
    .waitFor();
  await page.waitForTimeout(400);
  await page.screenshot({
    animations: "disabled",
    path: path.resolve("screenshots/evaluations.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: /智能问答/ }).click();
  await page.getByRole("heading", { name: "从一个好问题开始。" }).waitFor();
  await page.waitForTimeout(400);
  await page.screenshot({
    animations: "disabled",
    path: path.resolve("screenshots/chat-empty.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: /理解企业经营/ }).click();
  await page.getByRole("button", { name: "发送问题", exact: true }).click();
  await page
    .getByText("已找到以下相关原文。", { exact: false })
    .waitFor({ timeout: 180000 });
  await page.getByText("已完成", { exact: true }).first().waitFor();
  await page.waitForTimeout(400);
  await page.screenshot({
    animations: "disabled",
    path: path.resolve("screenshots/chat-answer.png"),
    fullPage: true,
  });
  await page.locator(".citation-chips button").first().click();
  await page.getByRole("heading", { name: "引用原文", exact: true }).waitFor();
  await page.waitForTimeout(400);
  await page.screenshot({
    animations: "disabled",
    path: path.resolve("screenshots/citation.png"),
    fullPage: true,
  });
  await page.getByRole('button',{name:'查看原文件',exact:true}).click();
  await page.locator('iframe.pdf-preview').waitFor();
  const pdfSrc=await page.locator('iframe.pdf-preview').getAttribute('src');
  if(!pdfSrc.includes('#page='))throw new Error('Citation did not preserve page target');
  await page.getByRole('button',{name:'关闭',exact:true}).click();
  await page.getByRole("button", { name: "关闭引用" }).click();
  await page.getByRole('button',{name:/知识库/}).first().click();
  await page.getByRole('button',{name:'上传文档',exact:true}).click();
  await page.locator('input[type=file]').setInputFiles({name:'browser-verification.txt',mimeType:'text/plain',buffer:Buffer.from('Browser verification revenue is 42 million in 2025. This is a local upload test.')});
  await page.getByRole('button',{name:'上传并解析'}).click();
  const row=page.getByRole('row').filter({hasText:'browser-verification.txt'});
  await row.getByText('已就绪',{exact:true}).waitFor({timeout:20000});
  page.once('dialog',dialog=>dialog.accept());
  await row.getByRole('button',{name:'删除 browser-verification.txt',exact:true}).click();
  await row.waitFor({state:'detached'});
  await page.getByRole('button',{name:/智能问答/}).click();
  await page.locator('.history-item.active').hover();
  await page.locator('.history-item.active .history-actions button').first().click();
  await page.getByRole('textbox',{name:'会话名称'}).fill('财报研究 · 前端验证');
  await page.getByRole('button',{name:'保存名称',exact:true}).click();
  await page.getByRole('button',{name:'财报研究 · 前端验证',exact:true}).waitFor();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(400);
  await page.screenshot({
    animations: "disabled",
    path: path.resolve("screenshots/mobile-chat.png"),
    fullPage: true,
  });
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
  if(overflow)throw new Error('Mobile layout has horizontal overflow');
  if (errors.length) throw new Error("Browser errors: " + errors.join(";"));
  console.log("Browser flow passed; 8 screenshots recorded.");
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
