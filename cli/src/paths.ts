import path from "node:path";
import os from "node:os";

/** Cross-platform config directory (Windows AppData / XDG-style elsewhere). */
export function configDir(): string {
  if (process.platform === "win32") {
    const base =
      process.env.APPDATA ?? path.join(os.homedir(), "AppData", "Roaming");
    return path.join(base, "abbieysearch");
  }
  const base =
    process.env.XDG_CONFIG_HOME ?? path.join(os.homedir(), ".config");
  return path.join(base, "abbieysearch");
}
