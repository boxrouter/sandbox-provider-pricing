# sandscale onboarding

Emitted by `make new-provider`; delete entries as they land, then this file.

- [ ] `billing.yaml`: set a `revisit` policy once the record read window is verified.
- [ ] `rules.py`, only if the provider's records need provider logic; the shared default rules
      read lifecycle times otherwise.
- [ ] `read-time.json`: the reviewed read-time declaration once the rules settle
      (docs/read-time-contract.md).
- [ ] `providers/sandscale/evidence/`: measurements for each `checks` entry (template in
      template/provider/evidence/).
- [ ] `fixtures/best/`: replace the scaffolded evidence with a recorded run; add fixtures as
      the record cases need them, then `make update-fixtures`.
