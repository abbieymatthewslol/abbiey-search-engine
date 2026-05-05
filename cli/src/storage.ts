import fs from "node:fs/promises";
import path from "node:path";
import { configDir } from "./paths.js";

export type PersistedState = {
  lastSearchUrl?: string;
  updatedAt?: string;
};

async function statePath(): Promise<string> {
  const dir = configDir();
  await fs.mkdir(dir, { recursive: true });
  return path.join(dir, "state.json");
}

export async function loadState(): Promise<PersistedState> {
  try {
    const raw = await fs.readFile(await statePath(), "utf8");
    return JSON.parse(raw) as PersistedState;
  } catch {
    return {};
  }
}

export async function saveState(patch: PersistedState): Promise<void> {
  const prev = await loadState();
  const next: PersistedState = {
    ...prev,
    ...patch,
    updatedAt: new Date().toISOString(),
  };
  await fs.writeFile(await statePath(), JSON.stringify(next, null, 2), "utf8");
}
