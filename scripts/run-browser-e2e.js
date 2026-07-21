const { spawn, spawnSync } = require("node:child_process");
const fs = require("node:fs");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");
const { once } = require("node:events");

const root = path.resolve(__dirname, "..");
const apiDir = path.join(root, "apps", "api");
const testScript = path.join(__dirname, "test-browser-e2e.js");
const outputDir = path.resolve(process.env.HEYU_E2E_OUTPUT || path.join(root, "outputs", "browser-e2e"));

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, options);
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (signal) {
        reject(new Error(`${command} exited after signal ${signal}`));
        return;
      }
      resolve(code ?? 1);
    });
  });
}

function findPython() {
  if (process.env.HEYU_PYTHON) return process.env.HEYU_PYTHON;
  const candidates =
    process.platform === "win32"
      ? [path.join(root, ".venv", "Scripts", "python.exe"), "python"]
      : [path.join(root, ".venv", "bin", "python"), "python3", "python"];
  return candidates.find((candidate) => {
    if (path.isAbsolute(candidate)) return fs.existsSync(candidate);
    const probe = spawnSync(candidate, ["--version"], { stdio: "ignore" });
    return !probe.error && probe.status === 0;
  });
}

function reservePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve(address.port);
      });
    });
  });
}

async function waitForHealth(baseUrl, server) {
  const deadline = Date.now() + 60_000;
  let lastError = null;
  while (Date.now() < deadline) {
    if (server.exitCode !== null) {
      throw new Error(`Local E2E API exited before becoming healthy (code ${server.exitCode}).`);
    }
    try {
      const response = await fetch(`${baseUrl}/health`, {
        signal: AbortSignal.timeout(1_000),
      });
      if (response.ok) return;
      lastError = new Error(`health returned ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Local E2E API did not become healthy: ${lastError?.message || "timeout"}`);
}

async function stopProcess(child) {
  if (!child || child.exitCode !== null) return;
  child.kill();
  await Promise.race([
    once(child, "exit"),
    new Promise((resolve) => setTimeout(resolve, 5_000)),
  ]);
  if (child.exitCode !== null) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  } else {
    child.kill("SIGKILL");
  }
}

async function main() {
  if (process.env.HEYU_BASE_URL) {
    const code = await run(process.execPath, [testScript], {
      cwd: root,
      env: process.env,
      stdio: "inherit",
    });
    process.exitCode = code;
    return;
  }

  const python = findPython();
  if (!python) {
    throw new Error("Python was not found. Run the Windows setup script or set HEYU_PYTHON.");
  }

  fs.mkdirSync(outputDir, { recursive: true });
  const runtimeDir = fs.mkdtempSync(path.join(os.tmpdir(), "heyu-browser-e2e-"));
  const databaseFile = path.join(runtimeDir, "heyu-browser-e2e.db").replace(/\\/g, "/");
  const databaseUrl = `sqlite:///${databaseFile}`;
  const port = await reservePort();
  const baseUrl = `http://127.0.0.1:${port}`;
  const logPath = path.join(outputDir, "local-e2e-api.log");
  const log = fs.createWriteStream(logPath, { flags: "w" });
  const env = {
    ...process.env,
    APP_ENV: "development",
    AUTO_CREATE_SCHEMA: "false",
    ABUSE_LIMITS_ENABLED: "false",
    DATABASE_URL: databaseUrl,
    PYTHONUTF8: "1",
  };
  let server = null;

  try {
    console.log(`Preparing isolated browser E2E database: ${databaseFile}`);
    const migrationCode = await run(python, ["-m", "alembic", "upgrade", "head"], {
      cwd: apiDir,
      env,
      stdio: "inherit",
    });
    if (migrationCode !== 0) {
      throw new Error(`Browser E2E database migration failed with exit code ${migrationCode}.`);
    }

    server = spawn(
      python,
      ["-m", "uvicorn", "e2e_app:app", "--host", "127.0.0.1", "--port", String(port)],
      {
        cwd: apiDir,
        env,
        stdio: ["ignore", log, log],
      },
    );
    await waitForHealth(baseUrl, server);
    console.log(`Running browser E2E against isolated API: ${baseUrl}`);

    const testCode = await run(process.execPath, [testScript], {
      cwd: root,
      env: {
        ...process.env,
        HEYU_BASE_URL: baseUrl,
        HEYU_E2E_OUTPUT: outputDir,
      },
      stdio: "inherit",
    });
    if (testCode !== 0) {
      throw new Error(`Browser E2E failed with exit code ${testCode}. API log: ${logPath}`);
    }
  } finally {
    await stopProcess(server);
    await new Promise((resolve) => log.end(resolve));
    fs.rmSync(runtimeDir, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
