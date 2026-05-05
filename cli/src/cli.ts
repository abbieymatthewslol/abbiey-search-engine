import { Command } from "commander";
import pkg from "../package.json" with { type: "json" };
import { mergeEnv, defaultConfig } from "./config.js";
import { checkOrigin } from "./doctor.js";
import { openUrl } from "./open-url.js";
import { readStdinText } from "./stdin.js";
import { loadState, saveState } from "./storage.js";
import { theme, hr } from "./theme.js";
import {
  buildImgOpsUrl,
  buildSearchUrl,
  type AnswerStyle,
  type Depth,
  type Evidence,
  type SearchMode,
} from "./urls.js";

function parsePairs(values: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const raw of values) {
    const idx = raw.indexOf("=");
    if (idx <= 0) {
      throw new Error(`Invalid --param "${raw}". Use name=value.`);
    }
    const name = raw.slice(0, idx).trim();
    const value = raw.slice(idx + 1).trim();
    if (!name) throw new Error(`Invalid --param "${raw}".`);
    out[name] = value;
  }
  return out;
}

function pickDepth(raw?: string): Depth | undefined {
  if (!raw) return undefined;
  const allowed = new Set<Depth>(["quick", "standard", "deep-research"]);
  if (!allowed.has(raw as Depth)) {
    throw new Error(`Unknown depth "${raw}". Try: quick | standard | deep-research`);
  }
  return raw as Depth;
}

function pickEvidence(raw?: string): Evidence | undefined {
  if (!raw) return undefined;
  const allowed = new Set<Evidence>(["links-only", "key-quotes", "full-excerpts"]);
  if (!allowed.has(raw as Evidence)) {
    throw new Error(
      `Unknown evidence "${raw}". Try: links-only | key-quotes | full-excerpts`,
    );
  }
  return raw as Evidence;
}

function pickAnswerStyle(raw?: string): AnswerStyle | undefined {
  if (!raw) return undefined;
  const allowed = new Set<AnswerStyle>(["direct", "balanced", "adversarial"]);
  if (!allowed.has(raw as AnswerStyle)) {
    throw new Error(
      `Unknown answer style "${raw}". Try: direct | balanced | adversarial`,
    );
  }
  return raw as AnswerStyle;
}

function pickMode(raw?: string): SearchMode | undefined {
  if (!raw) return undefined;
  const allowed = new Set<SearchMode>(["web", "research"]);
  if (!allowed.has(raw as SearchMode)) {
    throw new Error(`Unknown mode "${raw}". Try: web | research`);
  }
  return raw as SearchMode;
}

async function resolveQuery(
  explicit: string[] | undefined,
  opts: { stdin: boolean },
): Promise<string> {
  const parts = explicit?.filter(Boolean) ?? [];
  const stdinDash = parts.length === 1 && parts[0] === "-";
  const argvParts = (stdinDash ? [] : parts).join(" ").trim();

  let stdinText: string | undefined;
  if (opts.stdin || stdinDash) {
    stdinText = await readStdinText();
  }

  const merged = [argvParts, stdinText].filter(Boolean).join(" ").trim();
  if (!merged) {
    throw new Error(
      [
        "Missing query.",
        'Example:  abbiey search "tailwind arbitrary variants"',
        "Pipe:      echo explain RPO vs RTO | abbiey search --stdin",
        "Dash:      abbiey search -   # reads stdin until EOF",
      ].join("\n          "),
    );
  }
  return merged;
}

const program = new Command();

program
  .name("abbiey")
  .description(
    "abbieysearch from the terminal — shareable search URLs with the same controls as the web experience.",
  )
  .version(pkg.version, "-V, --version")
  .configureHelp({
    sortSubcommands: true,
    subcommandTerm: (cmd) => cmd.name(),
  });

program
  .command("search")
  .alias("s")
  .description("Compose a search URL (and optionally open it in your browser).")
  .argument("[query...]", "Search words; use quotes for a phrase.")
  .option("-o, --open", "Open the URL in your default browser")
  .option("--print-only", "Print the URL only (no framing text)", false)
  .option("--json", "Print JSON { url, query } on one line", false)
  .option("--stdin", "Read query text from stdin (also implied when query is '-')", false)
  .option("--origin <url>", "Override abbieysearch origin (see env ABBIEYSEARCH_ORIGIN)")
  .option("--depth <level>", "Depth: quick | standard | deep-research", (v) => v)
  .option(
    "--evidence <mode>",
    "Evidence: links-only | key-quotes | full-excerpts",
    (v) => v,
  )
  .option("--style <mode>", "Answer style: direct | balanced | adversarial", (v) => v)
  .option("--mode <mode>", "Search mode: web | research", (v) => v)
  .option(
    "--param <name=value>",
    "Append an extra query parameter (repeatable)",
    (value, prev: string[]) => {
      prev.push(value);
      return prev;
    },
    [],
  )
  .addHelpText(
    "after",
    () => `
Examples:
  ${theme.dim("$")} abbiey search "solid state battery supply chain"
  ${theme.dim("$")} abbiey search --depth deep-research --style balanced --open
  ${theme.dim("$")} echo "explain RPO vs RTO" | abbiey search --stdin --json
`,
  )
  .action(async (queryParts: string[], opts) => {
    const baseConfig = mergeEnv(defaultConfig());
    const origin = opts.origin?.trim() || baseConfig.origin;

    const depth = pickDepth(opts.depth?.trim()) ?? baseConfig.depth;
    const evidence = pickEvidence(opts.evidence?.trim()) ?? baseConfig.evidence;
    const answerStyle =
      pickAnswerStyle(opts.style?.trim()) ?? baseConfig.answerStyle;
    const mode = pickMode(opts.mode?.trim()) ?? baseConfig.mode;

    const extraList: string[] = Array.isArray(opts.param) ? opts.param : [];
    const extra = parsePairs(extraList);

    const query = await resolveQuery(queryParts, { stdin: Boolean(opts.stdin) });
    const url = buildSearchUrl({
      origin,
      query,
      depth,
      evidence,
      answerStyle,
      mode,
      extra,
    });

    await saveState({ lastSearchUrl: url });

    if (opts.json) {
      process.stdout.write(`${JSON.stringify({ url, query, origin })}\n`);
    } else if (opts.printOnly) {
      process.stdout.write(`${url}\n`);
    } else {
      process.stdout.write(`\n${theme.dim("abbieysearch")}\n`);
      process.stdout.write(`${hr()}\n`);
      process.stdout.write(`${theme.bold("Search")}\n\n`);
      process.stdout.write(`${theme.dim("query")}  ${query}\n`);
      process.stdout.write(`${theme.dim("open")}    ${theme.accent(url)}\n`);
      process.stdout.write(`${hr()}\n\n`);
    }

    if (opts.open) {
      openUrl(url);
      if (!opts.json && !opts.printOnly) {
        process.stdout.write(`${theme.dim("Opened in your default browser.")}\n`);
      }
    }
  });

program
  .command("image")
  .alias("i")
  .description(
    "Open ImgOps for reverse search and image metadata (same entry point as the site).",
  )
  .argument("<url>", "Direct image URL (https://...)")
  .option("-o, --open", "Open in browser (default on)", true)
  .option("--no-open", "Skip opening the browser")
  .option("--print-only", "Print URL only", false)
  .addHelpText(
    "after",
    () => `
Examples:
  ${theme.dim("$")} abbiey image "https://upload.wikimedia.org/wikipedia/commons/a/a7/Example.jpg"
`,
  )
  .action((imageUrl: string, opts) => {
    const url = buildImgOpsUrl(imageUrl);
    const autoOpen =
      opts.open &&
      !opts.printOnly &&
      process.env.CI !== "true";
    if (opts.printOnly) {
      process.stdout.write(`${url}\n`);
      return;
    }
    process.stdout.write(`\n${theme.dim("ImgOps")}  ${theme.accent(url)}\n\n`);
    if (autoOpen) {
      openUrl(url);
      process.stdout.write(`${theme.dim("Opened in your default browser.")}\n`);
    }
  });

program
  .command("open")
  .description("Open the last search URL created on this machine.")
  .option("--print-only", "Print URL without opening", false)
  .action(async (opts) => {
    const state = await loadState();
    const url = state.lastSearchUrl;
    if (!url) {
      process.stderr.write(
        `${theme.err("No recent search URL found.")} Run ${theme.bold("abbiey search")} first.\n`,
      );
      process.exitCode = 1;
      return;
    }
    if (opts.printOnly) {
      process.stdout.write(`${url}\n`);
      return;
    }
    openUrl(url);
    process.stdout.write(`${theme.dim("Opened last search.")}\n`);
    process.stdout.write(`${theme.accent(url)}\n`);
  });

program
  .command("doctor")
  .description("Verify network reachability and environment.")
  .action(async () => {
    const cfg = mergeEnv(defaultConfig());
    process.stdout.write(`\n${theme.bold("abbiey doctor")}\n${hr()}\n`);
    process.stdout.write(`${theme.dim("Node")}     ${process.version}\n`);
    process.stdout.write(`${theme.dim("Origin")}   ${cfg.origin}\n`);
    process.stdout.write(`${theme.dim("Platform")} ${process.platform}\n`);

    const res = await checkOrigin(cfg.origin);
    process.stdout.write(
      `${theme.dim("HEAD /")}   ${res.ok ? theme.accent(res.message) : theme.err(res.message)}\n`,
    );
    process.stdout.write(`${hr()}\n\n`);
    if (!res.ok) process.exitCode = 1;
  });

program
  .command("completion")
  .description("Print shell completion snippets (manual install).")
  .argument("<shell>", "bash | zsh | fish")
  .action((shell: string) => {
    const name = shell.trim().toLowerCase();
    if (name === "bash") {
      process.stdout.write(`_abbiey_completions() {
  local cur="\${COMP_WORDS[COMP_CWORD]}"
  if [ "\${COMP_CWORD}" -le 1 ]; then
    COMPREPLY=( $(compgen -W "search s image i open doctor completion home help --version --help" -- "\${cur}") )
    return
  fi
  case "\${COMP_WORDS[1]}" in
    search|s)
      COMPREPLY=( $(compgen -W "--open --print-only --json --stdin --depth --evidence --style --mode --origin --param --help" -- "\${cur}") )
      ;;
    image|i)
      COMPREPLY=( $(compgen -W "--open --print-only --help" -- "\${cur}") )
      ;;
    open)
      COMPREPLY=( $(compgen -W "--print-only --help" -- "\${cur}") )
      ;;
    doctor)
      COMPREPLY=( $(compgen -W "--help" -- "\${cur}") )
      ;;
    completion)
      COMPREPLY=( $(compgen -W "bash zsh fish" -- "\${cur}") )
      ;;
    *)
      COMPREPLY=()
      ;;
  esac
}
complete -F _abbiey_completions abbiey
`);
      return;
    }
    if (name === "zsh") {
      process.stdout.write(`# See abbiey completion bash for a simpler pattern, or use:
#  abbiey search <tab> flags are best completed by your zsh generic completer
`);
      return;
    }
    if (name === "fish") {
      process.stdout.write(`complete -c abbiey -n "__fish_use_subcommand" -a "search" -d "Search URL"
complete -c abbiey -n "__fish_use_subcommand" -a "image" -d "ImgOps URL"
complete -c abbiey -n "__fish_use_subcommand" -a "open" -d "Open last URL"
complete -c abbiey -n "__fish_use_subcommand" -a "doctor" -d "Diagnostics"
complete -c abbiey -n "__fish_use_subcommand" -a "home" -d "Home URL"
complete -c abbiey -n "__fish_seen_subcommand_from search" -s o -l open
complete -c abbiey -n "__fish_seen_subcommand_from search" -l json
`);
      return;
    }
    process.stderr.write(
      `${theme.err(`Unknown shell "${shell}".`)} Use bash, zsh, or fish.\n`,
    );
    process.exitCode = 1;
  });

program
  .command("home")
  .description("Print the homepage URL.")
  .action(() => {
    const cfg = mergeEnv(defaultConfig());
    const u = new URL("/", cfg.origin.replace(/\/+$/, "")).toString();
    process.stdout.write(`${u}\n`);
  });

async function maybeBareAlias(argv: string[]): Promise<boolean> {
  const skip = new Set(["-V", "--version", "-h", "--help"]);
  const tokens = argv.slice(2).filter((t) => !skip.has(t));
  if (tokens.length === 0) return false;
  const subcommands = new Set([
    "search",
    "s",
    "image",
    "i",
    "open",
    "doctor",
    "completion",
    "home",
    "help",
  ]);
  const first = tokens[0];
  if (!first || subcommands.has(first)) return false;

  await program.parseAsync(["search", ...tokens], {
    from: "user",
  });
  return true;
}

const argv = process.argv;
maybeBareAlias(argv)
  .then((handled) => {
    if (!handled) return program.parseAsync(argv);
  })
  .catch((err: unknown) => {
    const msg = err instanceof Error ? err.message : String(err);
    process.stderr.write(`${theme.err(msg)}\n`);
    process.exitCode = 1;
  });
