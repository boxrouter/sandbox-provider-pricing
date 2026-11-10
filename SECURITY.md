# Security

## Reporting a vulnerability

Report a vulnerability privately through GitHub: on this repository's **Security** tab,
choose **Report a vulnerability**. If GitHub's private reporting form is unavailable, email
the maintainers at [security@boxrouter.ai](mailto:security@boxrouter.ai). Please do not open a
public issue or pull request for it.

The maintainers will acknowledge the report within 7 days, keep you informed while it is
fixed, and credit you when it is disclosed, unless you prefer otherwise.

## Scope

In scope is the code in this repository: the calculator, the quote checker and the
price-drafting agent. Examples are a fetch that writes outside its output file, and a draft
that is accepted when its quotes are not on the page.

A vulnerability in a provider's service or SDK belongs to that provider: report it to them.
A wrong price is not a vulnerability: correct it as [CONTRIBUTING.md](CONTRIBUTING.md) says.

## Supported versions

Fixes go into the latest release.
