# Watching prices

Every rate in a price version comes with a verbatim quote from the provider's page. The `spp`
command checks that those quotes are still there and, when one is gone, has an agent draft the new
version for you to review. Neither command ever writes a price file on its own.

## Check the quotes

```sh
.venv/bin/spp check src/sandbox_provider_pricing/providers/e2b/prices/2026-10-20-061802Z.yaml
```

`spp check` fetches every source URL of each price version you name and looks for each stored
quote on the page, matching text with tags stripped and spacing ignored. A quote can join separate
excerpts of a page with ` | `; each excerpt must be on the page. Decorative `aria-hidden` text is
ignored (Modal draws each digit twice), and text a site ships only as JSON inside a script counts
(Vercel's API reference does this).

It prints one JSON line per version, whose `status` is one of:

| Status | Meaning |
| --- | --- |
| `confirmed` | Every quote was found. |
| `changed` | A page was read and a quote is gone. The quotes are listed under `missing`. |
| `unreadable` | A page could not be fetched. The pages are listed under `unreadable`. |

The exit status is 0 only when every version is confirmed.

## The daily run

The `Price watch` workflow runs `scripts/watch_prices.py` every day. BoxRouter's watchdog
starts it, because GitHub's own schedule arrives hours late or not at all. For each provider it
checks the current (newest, not superseded) price version, and keeps one issue per provider:

- `changed` or `unreadable`: the issue `Price check: <provider>` is opened, or its text rewritten when the
  result differs. A changed quote lists the quotes gone from the page.
- `confirmed`: the open issue, if any, is closed.

It never runs `spp draft` and never writes a price: a `changed` issue is for a person to turn into a new
price version. A new provider is watched as soon as its first price version is bundled.

```sh
uv run --locked python scripts/watch_prices.py --run-url "$URL" --provider e2b   # needs gh and a repository
```

## Draft a new version

When a page has changed, save it and ask for a draft:

```sh
ANTHROPIC_API_KEY=... .venv/bin/spp draft --page saved-page.html \
  src/sandbox_provider_pricing/providers/e2b/prices/2026-10-20-061802Z.yaml
```

`spp draft` needs the `draft` extra, which brings the Claude Agent SDK and its bundled Claude Code
binary. `check` and `reconcile` do not. Build the wheel and install it with the extra:

```sh
uv build --wheel
uv pip install --python .venv/bin/python "$(ls dist/sandbox_provider_pricing-*.whl)[draft]"
```

The agent (`sandbox_provider_pricing.watch.agent.MODEL`) reads the saved page and writes the version
again with fresh quotes. It has no tools and none of the machine's Claude settings. The key is read
only from `ANTHROPIC_API_KEY`.

Code, not the agent, decides whether to believe the draft (`watch.verify`, which uses no AI). A
draft is rejected unless:

- every quote it takes from the page is on the page;
- every unit rate is a number inside a quote about that resource, so a CPU price cannot come from
  the memory table;
- each rate's time unit, and GB or GiB, match its quote, and the calculator prices an hour of it as
  the quote does;
- it validates against the price-version schema.

A rejected draft is retried once with the failures listed. Quotes from the version's other pages
are kept as they were. The version id, `effective_from` and `retrieved_at` come from the clock.

The last line printed says what happened:

| Last line | Meaning | Exit status |
| --- | --- | --- |
| `reworded` | The verified draft has the same rates, meter rules and exclusions. Only the wording moved. | 0 |
| `price changed: cpu 0.000014 -> 0.000016` | The verified draft differs. A rate or meter rule shows as `<name> <old> -> <new>` and an exclusion as `exclusion: <old> -> <new>`, with `none` for one added or dropped. | 0 |
| `unreadable` | No verified draft after two tries. The failures are listed above it. | 1 |

Exit status 2 means drafting could not start: no key, no page, or Claude could not be reached.

`--out <file>` writes the verified draft as YAML; nothing else is written. `--url` names the page
when the quotes do not make it clear. A changed exclusion, such as a new plan fee, counts as a
price change. Review the draft and open a pull request with it as a new price version
([adding a provider](adding-a-provider.md) shows the checks it must pass).

## Compare a bill with the rates

```sh
.venv/bin/spp reconcile providers/vercel/evidence/reconciliations/2026-10-06
```

`spp reconcile` reads a normalized bill (`bill.jsonl`) and multiplies each row's quantity by the
rate in effect at the row's period start. [METHOD.md](../METHOD.md#checking-against-a-bill) says
how to normalize a bill and what counts as a match. The directory's `how.md` records how its
bill was exported.
