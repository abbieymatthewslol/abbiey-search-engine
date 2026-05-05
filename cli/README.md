# abbieysearch CLI

This package lives in the [`abbiey-search-engine-2`](https://github.com/abbieymatthewslol/abbiey-search-engine-2) repository under **`cli/`**.

Terminal helpers for **[abbieysearch](https://abbieysearch.com)** — build the same `/search` URLs the web UI uses (depth, evidence, answer style), open ImgOps for image tooling, and keep automation-friendly `--json` output.

Privacy-wise, this CLI runs locally: it does not send your query to Node’s maintainers or a third-party CLI vendor. Opening a URL loads the search in your browser under the site’s normal terms.

## Requirements

- **Node.js 18+** (ships with `fetch`, which `abbiey doctor` uses)

## Install (global, all platforms)

Pick one package manager:

```bash
npm install -g abbieysearch-cli
```

```bash
pnpm add -g abbieysearch-cli
```

```bash
yarn global add abbieysearch-cli
```

```bash
bun add -g abbieysearch-cli
```

Verify:

```bash
abbiey --version
abbiey doctor
```

### Try before you install

```bash
npx abbieysearch-cli@latest doctor
npx abbieysearch-cli@latest search "rust error e0382" --print-only
```

### From this repository (while developing)

```bash
git clone <your-repo-url> abbieysearch-cli
cd abbieysearch-cli
npm install
npm run build
npm link          # puts `abbiey` on your PATH for this checkout
```

## Commands

| Command | Purpose |
| --- | --- |
| `abbiey search <query>` | Compose a search URL; add `--open` to launch the default browser |
| `abbiey image <url>` | Open ImgOps for reverse search / metadata (same flow the site links to) |
| `abbiey open` | Reopen the last search URL generated on this machine |
| `abbiey doctor` | Quick environment + connectivity check |
| `abbiey home` | Print the configured site origin |
| `abbiey completion <bash\|zsh\|fish>` | Print starter completion scripts |

Shorthand: `abbiey s …` and `abbiey i …`.

Power-user shorthand: `abbiey rust ownership` is treated like `abbiey search rust ownership`.

## Flags that mirror the product

```bash
abbiey search "query" \
  --depth deep-research \
  --evidence key-quotes \
  --style adversarial \
  --mode research
```

Repeatable extras (for experiments or server-side flags you add later):

```bash
abbiey search "query" --param tbs=qdr:y --param safe=off --print-only
```

## Scripting & automation

Machine-readable line (great for CI or editor integrations):

```bash
abbiey search "kafka consumer lag" --json
```

Pipe a query explicitly (required when stdin is not a TTY such as some CI runners):

```bash
echo "explain drift detection" | abbiey search --stdin --json
```

URL only:

```bash
abbiey search "postgresql indexing" --print-only
```

## Environment variables

| Variable | Effect |
| --- | --- |
| `ABBIEYSEARCH_ORIGIN` | Override base URL (defaults to `https://abbieysearch.com`) |
| `ABBIEYSEARCH_DEPTH` | Default `--depth` |
| `ABBIEYSEARCH_EVIDENCE` | Default `--evidence` |
| `ABBIEYSEARCH_ANSWER_STYLE` | Default `--style` |
| `ABBIEYSEARCH_MODE` | Default `--mode` (`web` or `research`) |
| `ABBIEY_ORIGIN` | Alias of `ABBIEYSEARCH_ORIGIN` |
| `NO_COLOR` | Disable ANSI styling |
| `CI=true` | Disables implicit browser opens for `abbiey image` |

Configuration files live next to normal OS conventions (`~/.config/abbieysearch` on Unix-likes, `%AppData%/abbieysearch` on Windows) — currently used for remembering the last search URL (`state.json`).

## Embed on your developer page

Minimal copy-ready block:

```bash
npm install -g abbieysearch-cli
abbiey doctor && abbiey search "your stack + symptom" --open
```

Optional completion install:

```bash
abbiey completion bash >> ~/.bashrc
```

## License

MIT
