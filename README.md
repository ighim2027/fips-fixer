# fips-fixer

County FIPS codes change. Agencies don't update in lockstep. If you inner-join a CDC dataset to an EPA dataset on raw FIPS, you will silently drop rows and nothing will warn you.

No dependencies. Python 3.8+.

```python
from fips_fixer import normalize, audit_join, print_audit

normalize("46113")    # -> "46102"   Shannon renamed to Oglala Lakota
normalize("1001")     # -> "01001"   restore the leading zero
normalize("46113.0")  # -> "46102"   pandas turned your ints into floats

print_audit(audit_join(cdc_fips, epa_fips, "cdc", "epa"))
```

## The demo

Run `python fips_fixer.py`. Two lists of 6 codes that refer to *mostly the same counties*. A raw `set(a) & set(b)` matches **one**. After normalization, five.

That's a 5-in-6 silent data loss on a join that looked fine.

## Three kinds of change, and only one is fixable

**Renames and absorptions (1:1).** Shannon SD → Oglala Lakota. Bedford City VA absorbed into Bedford County. These live in `RECODES` and a lookup table solves them completely.

**Splits (1:many).** Broomfield County CO was created in 2001 out of pieces of Adams, Boulder, Jefferson, and Weld. Valdez-Cordova AK dissolved into Chugach and Copper River in 2019. **No dictionary can fix these.** If your 1999 dataset has Boulder County and your 2010 dataset has Boulder *and* Broomfield, the Boulder rows aren't measuring the same place, and reconciling them needs areal or population-weighted apportionment plus an assumption you have to defend.

This library will not guess. `audit_join` detects when a split child and its parent appear across your two datasets and prints a warning, because that's a vintage mismatch that produces double-counted population and it will not show up as a failed join.

**Redefinitions (n:m).** Connecticut abolished its 8 counties in favor of 9 planning regions for statistical purposes in 2022. The new boundaries cut across the old ones. Census uses the new codes; most health datasets still use the old ones. There is no crosswalk that preserves county-level counts. These are in `UNMAPPABLE` and `normalize()` returns `None` for them, which forces you to handle it.

## The design principle

Every failure is loud. `normalize()` raises on garbage rather than returning the input unchanged. Unmappable codes return `None` rather than passing through. `audit_join` reports unparseable rows, dropped rows, and split-vintage collisions as separate categories instead of collapsing them into a match rate.

The whole reason this problem bites people is that the failure mode is *silent*. A library that fixed 90% of cases quietly would be worse than nothing.

## Coverage warning

`RECODES` and `SPLITS` are **incomplete**. They contain the handful of changes I could verify against Census and CDC/NCHS documentation:

- Census, [Substantial Changes to Counties and County Equivalent Entities: 1970–Present](https://www.census.gov/programs-surveys/geography/technical-documentation/county-changes.html)
- CDC/NCHS, County Geography documentation

Note the agencies don't even agree with each other: NCHS dates the Oglala Lakota change to 2014, Census to 2015. Alaska in particular reorganizes boroughs and census areas frequently and is under-covered here. Virginia's independent-city mergers go back further than the entries listed.

**Do not treat a clean audit as proof your join is correct.** It proves you didn't hit a *known* problem.

## Tests

```bash
python -m unittest test_fips_fixer -v
```

13 tests. The one that matters is `test_raw_join_is_a_disaster`.

