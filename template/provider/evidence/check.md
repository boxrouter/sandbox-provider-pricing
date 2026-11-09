# TODO Check title (for example: Billing boundary against per-sandbox billed time)

**Date:** TODO YYYY-MM-DD. **Provider:** TODO. **Result:** TODO one sentence, including what
the check could not settle.

## Question

TODO The billing question this check answers, and why the provider's documentation does not
answer it.

## Method

- Sandboxes: TODO how many, size (CPU, memory, disk), region, image, and whether each
  image was cold (never pulled by this account) or cached.
- What we did: TODO the calls made and how long each sandbox ran. Name the SDK or API
  and its version.
- Our times: for every call, the moment it was sent and the moment it returned, from our
  own clock.
- The provider's figures: TODO the provider API or export read, when it was read, and
  any normalization (unit conversions are written out).

## Results

TODO One row per sandbox. Give offsets as provider figure minus our edge, in milliseconds;
negative means the provider's figure came first.

| # | Image | Provider start − create sent (ms) | Provider start − create returned (ms) | Provider end − destroy sent (ms) | Provider end − destroy returned (ms) | Billed (s) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | TODO | | | | | |

## Verdict

TODO What the evidence supports, how strongly, and what it rules out. Say plainly what it
does not settle and what would.

## Limits

TODO Sample size, image cases not covered, account or plan specifics, anything that could
make the result differ elsewhere.
