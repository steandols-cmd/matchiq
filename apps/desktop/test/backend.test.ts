// Integrationstest av sidecar-protokollet: startar den riktiga Python-backend i utvecklingsläge,
// väntar på READY-raden och kontrollerar tokenskyddet. Körs med `npm test` (Node, utan Electron).
import { test } from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { apiGet, resolveBackendCommand, startBackend } from "../src/backend";

const repoRoot = path.resolve(__dirname, "..", "..", "..", "..");

test("backend startar, binds till 127.0.0.1 och kräver token", { timeout: 90_000 }, async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "matchiq-desktop-test-"));
  const cmd = resolveBackendCommand(false, "", repoRoot);
  const b = await startBackend({ ...cmd, dataDir, extraArgs: ["--no-sync"], env: { ...(cmd.env || {}), MATCHIQ_SECRETS: "memory" } });
  try {
    assert.ok(b.port > 0);
    assert.equal(b.baseUrl, `http://127.0.0.1:${b.port}`);
    const meta = await apiGet<any>(b, "/meta");
    assert.equal(meta.status, 200);
    assert.equal(meta.body.app, "MatchIQ");
    assert.equal(meta.body.data_dir, fs.realpathSync(dataDir));
    const unauth = await apiGet<any>({ port: b.port, token: "fel" }, "/meta");
    assert.equal(unauth.status, 401);
    const sched = await apiGet<any>(b, "/scheduler");
    assert.equal(sched.body.running, true);
    assert.ok(fs.existsSync(path.join(dataDir, "matchiq.sqlite")));
  } finally {
    await b.stop();
  }
  assert.ok(b.proc.exitCode !== null || b.proc.killed);
});
