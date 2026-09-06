/**
 * The Vouch bridge.
 *
 * Vouch's memory core is Python (Sibyl Memory is a Python SDK); the Virtuals
 * ACP SDK is Node. Rather than reimplement the memory layer, this shells out to
 * the same machine-readable CLI any other agent would use:
 *
 *   vouch decide  --handle X --price N   -> should I take this job?
 *   vouch record  --handle X --kind ...  -> log what they did
 *   vouch rate    --handle X --publish   -> seal evidence, write to Base
 *   vouch lookup  --handle X             -> what does memory know?
 *
 * That is deliberate. The integration surface an outside team would use is the
 * one our own ACP agent uses, so it cannot rot.
 */

import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";
import fs from "node:fs";

const execFileAsync = promisify(execFile);

const ROOT = path.resolve(import.meta.dirname, "..");

function pythonBin() {
  if (process.env.VOUCH_PYTHON) return process.env.VOUCH_PYTHON;
  const venvWin = path.join(ROOT, ".venv", "Scripts", "python.exe");
  const venvNix = path.join(ROOT, ".venv", "bin", "python");
  if (fs.existsSync(venvWin)) return venvWin;
  if (fs.existsSync(venvNix)) return venvNix;
  return "python";
}

async function run(args) {
  const { stdout } = await execFileAsync(pythonBin(), ["-m", "vouch", ...args], {
    cwd: ROOT,
    env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    maxBuffer: 8 * 1024 * 1024,
  });
  try {
    return JSON.parse(stdout);
  } catch {
    throw new Error(`vouch ${args[0]} did not return JSON:\n${stdout}`);
  }
}

/** Should this job be accepted, repriced, escrowed, or refused? */
export async function decide(handle, { price = 0, jobRef = null } = {}) {
  const args = ["decide", "--handle", handle, "--price", String(price)];
  if (jobRef) args.push("--job-ref", jobRef);
  return run(args);
}

/** Log an outcome. This is the write that changes the next decision. */
export async function record(handle, { kind, detail, jobRef = null, agentId = null, flag = false } = {}) {
  const args = ["record", "--handle", handle, "--kind", kind, "--detail", detail];
  if (jobRef) args.push("--job-ref", jobRef);
  if (agentId != null) args.push("--agent-id", String(agentId));
  if (flag) args.push("--flag");
  return run(args);
}

/** Seal the evidence file; optionally publish the rating to Base. */
export async function rate(handle, { publish = false, subjectAgentId = null, network = "base-sepolia" } = {}) {
  const args = ["rate", "--handle", handle];
  if (publish) args.push("--publish", "--network", network);
  if (subjectAgentId != null) args.push("--subject-agent-id", String(subjectAgentId));
  return run(args);
}

/** Read the memory record for a counterparty. */
export async function lookup(handle) {
  return run(["lookup", "--handle", handle]);
}

export default { decide, record, rate, lookup };
