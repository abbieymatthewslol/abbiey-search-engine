# Documentation index

Use this folder as the non-code home for deployment notes, architecture context,
and project tracking.

## Start here

- [`GETTING-HELP.md`](./GETTING-HELP.md) - how to report issues and what to
  include when asking for help
- [`SELF-HOSTING.md`](./SELF-HOSTING.md) - deployment walkthroughs for Docker,
  Vercel, Render, Fly.io, and bare-metal setups
- [`API.md`](./API.md) - public API behavior, auth, billing, and rate-limit docs
- [`../cli/README.md`](../cli/README.md) - developer CLI (`abbiey`): URLs, ImgOps, scripting flags
- [`deep-web.md`](./deep-web.md) - Deep Web / Onion search behavior and caveats
- [`PROJECT-INDEX.md`](./PROJECT-INDEX.md) - current feature inventory, endpoint
  map, and architecture snapshot
- [`TODO.md`](./TODO.md) - completed roadmap items and historical project
  checklist

## Repository organization

- Keep the root focused on app entrypoints, deployment config, and top-level
  contributor files.
- Put contributor and architecture docs here in `docs/`.
- Keep operational helpers in `scripts/` so local utilities do not clutter the
  root.
