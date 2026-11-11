# agent37 onboarding

Emitted by `make new-provider`; delete entries as they land, then this file.

- [ ] First sourced price version: research the provider's pages, write the version YAML and
      its saved pages, then `spp scaffold agent37 --price sourced-price.yaml --sources
      saved-pages.json`. The provider joins the price sheet, cost method and generated docs
      only once a version is in effect.
- [ ] `billing.yaml`: replace the unknown answers with sourced ones; set a `revisit` policy
      once the record read window is verified.
- [ ] `rules.py`, only if the provider's records need provider logic; the shared default rules
      read lifecycle times otherwise.
- [ ] `read-time.json`: the reviewed read-time declaration once the rules settle
      (docs/read-time-contract.md).
- [ ] `providers/agent37/evidence/`: measurements for each `checks` entry (template in
      template/provider/evidence/).
- [ ] `fixtures/best/`: replace the scaffolded evidence with a recorded run; add fixtures as
      the record cases need them, then `make update-fixtures`.
