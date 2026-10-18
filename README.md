<p align="center">
  <img src="assets/branding/odysseus-wordmark.png" alt="Odysseus" width="238">
</p>

> [!NOTE]
> **About this branch.** `all-jgw3-fixes` is a demo branch on JGW3's personal fork of [Odysseus](https://github.com/odysseus-dev/odysseus). It is upstream `dev` with all of JGW3's open pull requests merged in, so the fixes can be tried together. It is not the official project and not a release. For the real thing, use [odysseus-dev/odysseus](https://github.com/odysseus-dev/odysseus).
>
> **Pull requests merged here:**
>
> - [#5965](https://github.com/odysseus-dev/odysseus/pull/5965): fix(gallery): raise vision max_tokens so thinking models return content
> - [#5968](https://github.com/odysseus-dev/odysseus/pull/5968): feat(chat): add Re-run button to the vision text editor
> - [#6019](https://github.com/odysseus-dev/odysseus/pull/6019): feat(gallery): AI-generated photo descriptions (OCR/captioning)
> - [#6148](https://github.com/odysseus-dev/odysseus/pull/6148): fix(chat): caption chat-uploaded images when the chat model is multimodal
> - [#6225](https://github.com/odysseus-dev/odysseus/pull/6225): fix(chat): warn before regenerate, resend or edit deletes later messages; offer fork
> - [#6597](https://github.com/odysseus-dev/odysseus/pull/6597): fix(gallery): drop the second scrollbar on the photo detail view
> - [#6617](https://github.com/odysseus-dev/odysseus/pull/6617): fix(ui): let confirm-dialog buttons grow to fit wrapped labels
>
> **What had to change to combine them** (this branch only; the pull requests themselves are unchanged):
>
> - #5965 and #6019 both raise the gallery vision `max_tokens` and change AI tagging. #6019 rewrites AI tagging around a shared vision call, so its version is used here (`VISION_MAX_TOKENS = 2000` instead of #5965's 1200).
> - Because of that rewrite, #5965's test `tests/test_ai_tag_thinking_response.py` is removed on this branch. It tests a helper (`_extract_ai_tag_response_text`) that #6019 replaces.
> - #6597 and #6617 both re-version the shared stylesheets and `app.js`. This branch uses one combined version tag (`20261017allfixes1`) and its own service-worker cache name (`odysseus-v661-all-jgw3-fixes`).
>
> **Testing:** the pull requests' own tests plus the frontend, version-parity, gallery, vision, chat-history and document tests (781 tests, browser tests included) pass, with no failures that clean upstream `dev` doesn't also have.


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
