<p align="center">
  <img src="assets/branding/odysseus-wordmark.png" alt="Odysseus" width="238">
</p>

> [!WARNING]
> **Work in progress: untested.** `wip/projects` is a feature branch on JGW3's personal fork of [Odysseus](https://github.com/odysseus-dev/odysseus). It is upstream `dev` plus a Projects feature that is still being built and hasn't been tested in daily use. It is not the official project and not a release. For the real thing, use [odysseus-dev/odysseus](https://github.com/odysseus-dev/odysseus).
>
> **Why Projects.** Memories and documents in Odysseus are global per account, so every chat can see everything. My poetry writing sessions don't need to know that I can't fix a lawnmower, and my astrology sessions don't need to know about my science degree. Folders group chats in the sidebar, but they don't keep anything apart. The per-chat memory switches work, but you have to flip them in every chat.
>
> **What this branch does:**
>
> - **Projects replace folders.** A project is still a chat's `folder` value, so existing folders become projects that share with Main, and nothing changes until you change a project's settings.
> - **Sidebar:** Projects sits above Chats. **Main (default)** is first and holds chats outside any project. Each project expands to show its chats, with a gear for its settings. Chats is one list of every chat, most recently used first.
> - **Project settings:**
>   - **Compartmentalized memory:** what the project remembers stays in it. It can start fresh, start with today's memories, or keep receiving Main's memories.
>   - **Compartmentalized documents:** documents made in the project stay in it, and the AI there only sees the project's documents.
>   - New projects start with both on.
> - **Main** sees everything except what compartmentalized projects keep to themselves.
> - **Moving a chat** asks whether its memories and documents go with it, but only when the move changes who can see them.
> - **Project page:** opened from the project's name or "manage". It has a description, a "New chat in <project>" box, recent chats, and the project's memories and files.
> - **Enforcement:** the AI's memory and document tools follow the project rules, and the built-in Memory MCP tool is left out where it can't. The Library and Memory windows still show you everything you own.
>
> **Why this isn't a pull request on odysseus-dev.** Projects has been requested in [#625](https://github.com/odysseus-dev/odysseus/issues/625), [#4868](https://github.com/odysseus-dev/odysseus/issues/4868) and [#4937](https://github.com/odysseus-dev/odysseus/issues/4937). Earlier Projects pull requests by others ([#2495](https://github.com/odysseus-dev/odysseus/pull/2495), [#2893](https://github.com/odysseus-dev/odysseus/pull/2893), [#5267](https://github.com/odysseus-dev/odysseus/pull/5267)) were closed without being merged, most of them in a July 2026 cleanup of the backlog, and [#6241](https://github.com/odysseus-dev/odysseus/pull/6241) is still waiting for review. The [roadmap](https://github.com/odysseus-dev/odysseus/blob/dev/ROADMAP.md)'s top priority is fixing bugs, and [CONTRIBUTING.md](https://github.com/odysseus-dev/odysseus/blob/dev/CONTRIBUTING.md) asks for an issue first and small pull requests for large features. So this lives here until the maintainers want it, and then it would go upstream as a few small pull requests.


<p align="center">
  A self-hosted AI workspace for chat, agents, research, documents, email, notes, calendar, and local model workflows.
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> ·
  <a href="website/setup.md">Setup Guide</a> ·
  <a href="CONTRIBUTING.md">Contributing</a> ·
  <a href="ROADMAP.md">Roadmap</a>
</p>

<p align="center">
  <a href="https://repology.org/project/odysseus-ai/versions"><img src="https://repology.org/badge/vertical-allrepos/odysseus-ai.svg" alt="Packaging status"></a>
</p>

<p align="center">
  <img src="assets/branding/odysseus-browser.jpg" alt="Odysseus interface">
</p>

---

## Quick Start

> `dev` is the default branch and gets the newest changes first. Use [`main`](https://github.com/odysseus-dev/odysseus/tree/main) if you want the more curated branch.

```bash
git clone https://github.com/odysseus-dev/odysseus.git
cd odysseus
cp .env.example .env
docker compose up -d --build
```

Open `http://localhost:7011` when the containers are healthy. The first admin password is printed in `docker compose logs odysseus`.

The compose files pull the official multi-arch image `ghcr.io/odysseus-dev/odysseus` (published by CI on every push to `main` and `dev`) and only build locally if the pull fails — so this also works on hosts without a build toolchain, e.g. as a [Portainer](https://www.portainer.io/) stack.

**Production deployments:** pin the immutable tag instead of `:latest`. `:latest` and bare `:X.Y.Z` tags move on every push to `main`, but `:X.Y.Z-<sha>` (e.g. `1.0.2-7c8070f`) always refers to one specific build:

```bash
ODYSSEUS_IMAGE=ghcr.io/odysseus-dev/odysseus:1.0.2-7c8070f docker compose up -d
```

Native installs, GPU notes, Windows/macOS instructions, HTTPS, and configuration live in the [setup guide](website/setup.md).

## Features

- **Chat + Agents** — local/API models, tools, MCP, files, shell, skills, and memory.
- **Cookbook** — hardware-aware model recommendations, downloads, and serving.
- **Deep Research** — multi-step web research with source reading and report generation.
- **Compare** — blind side-by-side model testing and synthesis.
- **Documents** — writing-first editor with AI edits, suggestions, Markdown, HTML, CSV, and syntax highlighting.
- **Email** — IMAP/SMTP inbox with triage, tags, summaries, reminders, and reply drafts.
- **Notes, Tasks + Calendar** — reminders, todos, scheduled agent tasks, and CalDAV sync.
- **Extras** — gallery/image editor, themes, uploads, web search, presets, sessions, and 2FA.

## Demo

A full hover-to-play tour lives on the [Odysseus landing page](https://odysseus-dev.github.io/odysseus/). Its source lives under [`website/`](website/).

## Contributing

Help is welcome. The best entry points are fresh-install testing, provider setup bugs, mobile/editor polish, docs, and small focused refactors. See [CONTRIBUTING.md](CONTRIBUTING.md) and [ROADMAP.md](ROADMAP.md).

## Security

Odysseus is a self-hosted workspace with powerful local tools. Keep auth enabled, keep private data out of Git, and do not expose raw model/service ports publicly.

- Keep `AUTH_ENABLED=true` for any network-accessible deployment.
- Keep `LOCALHOST_BYPASS=false` outside local development.

Deployment details are in the [setup guide](website/setup.md#security-notes).

## Community & Growth

<p align="center">
  <a href="https://trendshift.io/repositories/43167">
      <a href="https://trendshift.io/repositories/43167?utm_source=trendshift-badge&amp;utm_medium=badge&amp;utm_campaign=badge-trendshift-43167" target="_blank" rel="noopener noreferrer"><img src="https://trendshift.io/api/badge/trendshift/repositories/43167/monthly" alt="odysseus-dev%2Fodysseus | Trendshift" width="230"/></a>
  </a>
</p>

<p align="center">
  <a href="https://star-history.dera.page/#odysseus-dev/odysseus&type=date&legend=top-left">
    <picture>
      <source
        media="(prefers-color-scheme: dark)"
        srcset="https://star-history.dera.page/svg?repos=odysseus-dev/odysseus&type=date&theme=dark&legend=top-left"
      />
      <source
        media="(prefers-color-scheme: light)"
        srcset="https://star-history.dera.page/svg?repos=odysseus-dev/odysseus&type=date&legend=top-left"
      />
      <img
        src="https://star-history.dera.page/svg?repos=odysseus-dev/odysseus&type=date&legend=top-left"
        alt="Odysseus GitHub star history"
        width="100%"
      />
    </picture>
  </a>
</p>

## License

AGPL-3.0-or-later -- see [LICENSE](LICENSE) and [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md).
