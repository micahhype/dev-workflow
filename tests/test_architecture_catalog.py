"""Architecture catalog: designs cite entries by id and agents are briefed from the
`### ` index, so every entry must parse and every cross-reference must resolve."""
import os
import re

CATALOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "references", "architecture-patterns.md")

FIELDS = ["Signals", "Not when", "Cost", "Pairs with", "Conflicts with",
          "Overuse smell", "Simpler alternative"]
REFERENCE_FIELDS = {"Pairs with", "Conflicts with", "Simpler alternative"}
ID_LIST = re.compile(r"^(none|`[a-z0-9-]+`(, `[a-z0-9-]+`)*)$")
ENTRY_HEADING = re.compile(r"^### ([a-z0-9]+(?:-[a-z0-9]+)*) — [^:]+: \S")


def parse_entries():
    with open(CATALOG, encoding="utf-8") as catalog:
        sections = catalog.read().split("\n### ")[1:]
    entries = {}
    for section in sections:
        heading, *body = section.split("\n")
        match = ENTRY_HEADING.match("### " + heading)
        assert match, f"### line outside the entry format: {heading!r}"
        entry_id = match.group(1)
        assert entry_id not in entries, f"duplicate id {entry_id}"
        bullets = [line for line in body if line.startswith("- ")]
        entries[entry_id] = [bullet[2:].split(": ", 1) for bullet in bullets]
    return entries


def test_every_entry_has_the_seven_fields_in_order_and_non_empty():
    for entry_id, fields in parse_entries().items():
        assert [name for name, *_ in fields] == FIELDS, entry_id
        assert all(len(field) == 2 and field[1].strip() for field in fields), entry_id


def test_reference_fields_are_none_or_a_list_of_ids():
    for entry_id, fields in parse_entries().items():
        for name, value in fields:
            if name in REFERENCE_FIELDS:
                assert ID_LIST.match(value), f"{entry_id} {name}: {value!r}"


def test_every_referenced_id_is_an_entry():
    entries = parse_entries()
    for entry_id, fields in entries.items():
        for name, value in fields:
            if name in REFERENCE_FIELDS or name == "Not when":
                missing = set(re.findall(r"`([^`]+)`", value)) - set(entries)
                assert not missing, f"{entry_id} {name}: unknown {missing}"
