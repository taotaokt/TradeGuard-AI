# Screening sources and import notes

Last reviewed: 2026-10-20

TradeGuard does not silently download or activate a live list. An administrator first obtains an
approved source file, converts it to the documented CSV shape, imports it, checks the checksum and
entry count, and then activates that exact version. A failed import leaves the previous version active.

## Official starting points

- [OFAC Sanctions List Service](https://ofac.treasury.gov/sanctions-list-service) provides current
  U.S. Treasury SDN and consolidated non-SDN list downloads.
- [U.S. Consolidated Screening List](https://www.trade.gov/consolidated-screening-list) combines
  multiple Commerce, State, and Treasury export-screening sources. It is an aid to screening; a
  possible match still requires due diligence and checking the responsible agency's official record.
- [UK Sanctions List](https://www.gov.uk/government/publications/the-uk-sanctions-list) is the current
  UK designation source. The old OFSI Consolidated List closed on 28 January 2026.

These links are also recorded in `config/lists/sources.json`. They are reference landing pages rather
than hard-coded download URLs because agency delivery formats and endpoints can change.

## Import CSV

Required columns:

```text
source_id,name
```

Optional columns:

```text
entity_type,country,address,program,aliases,identifiers,remarks
```

- Separate aliases with `|`.
- Use a two-letter country code when a country is known.
- `identifiers` may contain a JSON object; non-JSON text is retained as a source value.
- Save the file as UTF-8 CSV.
- Every `source_id` must be unique inside a version.

The included file under `sample-data/screening/` is entirely fictional and must never be represented
as an official designation list.

## Matching behavior

Names are Unicode-normalized, punctuation is removed, common company suffixes are ignored, and the
system checks both exact and configurable fuzzy similarity. Legal name, aliases, and related parties
are screened. A score creates a review candidate only; it does not establish identity or a legal
restriction. A reviewer compares countries, identifiers, addresses, source programs, and evidence,
then records a classification and rationale.
