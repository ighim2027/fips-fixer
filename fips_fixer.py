#!/usr/bin/env python3
"""
fips-fixer: normalize county FIPS codes so datasets from different
agencies and different years will actually join.

The problem: county geographies change. Codes get retired, counties
merge, states reorganize. CDC, EPA, and Census don't update in lockstep.
If you inner-join two county datasets on raw FIPS you will silently drop
rows, and nothing will warn you.

Standard library only.

    from fips_fixer import normalize, audit_join

    normalize("46113")           -> "46102"   (Shannon -> Oglala Lakota)
    normalize("2")               -> "02000"   (zero-pad, state-level)
    audit_join(fips_a, fips_b)              # tells you what you're losing
"""

# --- Known recodes ----------------------------------------------------------
# 1:1 renames and absorptions. old FIPS -> current FIPS.
# Every entry has a source. This list is INCOMPLETE. See README.

RECODES = {
    # Shannon County SD renamed Oglala Lakota County. Census: 2015.
    # (CDC/NCHS says "effective 2014"; the agencies disagree by a year.)
    "46113": "46102",
    # Bedford City VA became a town, absorbed into Bedford County, 2013-07-01
    "51515": "51019",
    # Wade Hampton Census Area AK renamed Kusilvak Census Area, 2015
    "02270": "02158",
    # Clifton Forge City VA reverted to town, absorbed into Alleghany, 2001
    "51560": "51005",
    # Dade County FL renamed Miami-Dade, effective 1997-07-22 (Census)
    "12025": "12086",
}

# --- Splits: 1-to-many. A rename dict CANNOT fix these. ---------------------
# When a county is carved out of others, no code-level crosswalk exists.
# Old-vintage data for the parents includes population that now belongs to
# the child. Reconciling requires areal or population-weighted apportionment.
# We refuse to guess. We name the parents so you know what you're dealing with.

SPLITS = {
    # Broomfield County CO created 2001 from parts of Adams, Boulder,
    # Jefferson, and Weld.
    "08014": ["08001", "08013", "08059", "08123"],
    # Valdez-Cordova Census Area AK dissolved 2019 into Chugach (02063)
    # and Copper River (02066).
    "02063": ["02261"],
    "02066": ["02261"],
}

# Codes that exist in some datasets but have no clean county equivalent.
# Dropping these is correct, but it should be LOUD, not silent.
UNMAPPABLE = {
    # Connecticut replaced its 8 counties with 9 planning regions for
    # statistical purposes in 2022. Census uses 090xx; most health
    # datasets still use the old counties. There is no 1:1 crosswalk --
    # planning region boundaries cut across old county lines.
    "09110": "CT planning region (Capitol) -- no 1:1 county equivalent",
    "09120": "CT planning region (Greater Bridgeport)",
    "09130": "CT planning region (Lower CT River Valley)",
    "09140": "CT planning region (Naugatuck Valley)",
    "09150": "CT planning region (Northeastern CT)",
    "09160": "CT planning region (Northwest Hills)",
    "09170": "CT planning region (South Central CT)",
    "09180": "CT planning region (Southeastern CT)",
    "09190": "CT planning region (Western CT)",
    # Valdez-Cordova AK: dissolved 2019, split into two. Old-vintage data
    # keyed to 02261 cannot be assigned to a single successor.
    "02261": "Valdez-Cordova AK -- split into 02063 and 02066 in 2019",
}

# Non-state territories. Present in Census, usually absent from CDC/EPA.
TERRITORIES = {"60", "66", "69", "72", "78"}  # AS, GU, MP, PR, VI


class FipsError(ValueError):
    pass


def normalize(code, strict=False):
    """
    Return a canonical 5-digit county FIPS string.

    Handles: integer input, missing leading zeros, float artifacts from
    pandas ("46113.0"), and known recodes.

    Raises FipsError on unmappable codes when strict=True, otherwise
    returns None so you can filter them.
    """
    if code is None:
        raise FipsError("got None")

    s = str(code).strip()

    # pandas turns an int column with NaNs into floats. "46113.0"
    if s.endswith(".0"):
        s = s[:-2]

    if not s or not s.isdigit():
        raise FipsError(f"not numeric: {code!r}")

    # 4 digits almost always means a dropped leading zero (Alaska,
    # Alabama, Arizona...). 1-2 digits means state-level.
    if len(s) <= 2:
        s = s.zfill(2) + "000"
    elif len(s) == 4:
        s = "0" + s
    elif len(s) != 5:
        raise FipsError(f"unexpected length {len(s)}: {code!r}")

    if s in UNMAPPABLE:
        if strict:
            raise FipsError(f"{s}: {UNMAPPABLE[s]}")
        return None

    return RECODES.get(s, s)


def state_of(code):
    """Two-digit state FIPS from a county code."""
    return normalize(code)[:2]


def audit_join(left, right, left_name="left", right_name="right"):
    """
    Compare two collections of FIPS codes before you join them.
    Returns a report dict. Print it. Read it. Don't skip this.
    """
    def clean(codes):
        good, bad, dropped = set(), [], []
        for c in codes:
            try:
                n = normalize(c)
            except FipsError as e:
                bad.append((c, str(e)))
                continue
            if n is None:
                dropped.append(c)
            else:
                good.add(n)
        return good, bad, dropped

    l_good, l_bad, l_drop = clean(left)
    r_good, r_bad, r_drop = clean(right)

    only_left = l_good - r_good
    only_right = r_good - l_good
    both = l_good & r_good

    # A split child present in one set while its parent is present in the
    # other is NOT a clean match, even though both codes normalize fine.
    # This is the failure mode that produces double-counted population.
    split_warnings = []
    for child, parents in SPLITS.items():
        for parent in parents:
            if (child in l_good and parent in r_good) or (
                child in r_good and parent in l_good
            ):
                split_warnings.append(
                    f"{child} (child) and {parent} (parent) appear across "
                    f"datasets -- vintages differ, population may double-count"
                )

    return {
        f"{left_name}_count": len(l_good),
        f"{right_name}_count": len(r_good),
        "matched": len(both),
        f"only_in_{left_name}": sorted(only_left),
        f"only_in_{right_name}": sorted(only_right),
        "unparseable": l_bad + r_bad,
        "unmappable_dropped": sorted(set(l_drop + r_drop)),
        "split_geography_warnings": split_warnings,
        "match_rate": len(both) / max(len(l_good), 1),
    }


def print_audit(report):
    print("=" * 52)
    print("JOIN AUDIT")
    print("=" * 52)
    for k, v in report.items():
        if isinstance(v, list):
            if not v:
                continue
            print(f"\n{k}  ({len(v)})")
            for item in v[:10]:
                print(f"    {item}")
            if len(v) > 10:
                print(f"    ... and {len(v) - 10} more")
        elif isinstance(v, float):
            print(f"{k:<28}{v:.1%}")
        else:
            print(f"{k:<28}{v}")
    print()

    if report["match_rate"] < 0.95:
        print("!! match rate below 95%. Do not proceed until you know why.")
    if report["split_geography_warnings"]:
        print("!! split geography detected. Your datasets are different vintages.")


if __name__ == "__main__":
    # Two fake datasets that look joinable and are not.
    # 08014 vs 08013: Broomfield exists in one vintage, not the other.
    cdc = ["46113", "51515", "1001", "02270", "39049", "09110", "08013"]
    epa = ["46102", "51019", "01001", "02158", "39049", "39041", "08014"]

    print_audit(audit_join(cdc, epa, "cdc", "epa"))

    print("normalize() examples:")
    for c in ["46113", "1001", "46113.0", 39049, "2"]:
        print(f"  {str(c):<12} -> {normalize(c)}")
