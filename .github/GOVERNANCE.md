# Governance

## Maintainers

The maintainers decide what lands. Today they all work for BoxRouter, which
routes paid sandbox traffic to the providers listed here. BoxRouter's own prices, margins and
credits are not part of this repository.

The maintainers want these pages kept by the providers and the people who use them, and will change
these rules as they join. Someone who has contributed steadily becomes a maintainer when the
existing maintainers agree, and joins the maintainers list with their company.

## How a change lands

Anyone may open a pull request, or an issue first for a larger change. A change lands with one
maintainer's approval, and any maintainer's objection holds it until the maintainers agree.

Every change is judged by the same principles: list price, not your bill; the provider's own
figure first; unknown is never zero; every fact carries its source. [METHOD.md](../METHOD.md)
states them in full, and [CONTRIBUTING.md](../CONTRIBUTING.md) says what a correction or a new
provider must bring.

## Versions

A price version is named for its provider and date, and is in effect from its `effective_from`
until the next version. Once released it never changes; [formats](../docs/formats.md#price-versions)
explains why.

The package version lives in `pyproject.toml` and each release is tagged `vX.Y.Z`
([RELEASE.md](../RELEASE.md)). A change to a schema's meaning raises the minor version. New price
versions and documentation are patch releases.

## Provider pages

A provider may review and own its page. Someone who can show they speak for the provider, for
example as a member of its GitHub organization, asks in an issue. The maintainers then add them as
code owners for `providers/<provider>/`, and they review every change to that folder.

Evidence decides, whoever owns the page. Anyone may open a correction with evidence that a stated
value is wrong. The owner reviews it, and if the owner has not answered in 14 days a maintainer may
merge a correction whose evidence holds. Every provider is held to the same rules, including any
provider a maintainer works with.

Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).
