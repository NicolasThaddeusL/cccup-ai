# Merge & validate CC Cup data files listed in data.index.yaml
# Usage:
#   pip install pyyaml
#   python merge.py --index data.index.yaml --out ../data/data.bundle.yaml --json ../data/data.bundle.json

import argparse, os, sys, json, datetime

try:
    import yaml
except ImportError:
    sys.stderr.write("Missing dependency: pyyaml. Install with `pip install pyyaml`.\n")
    sys.exit(1)

# Known sections the bundler will lift to the top-level bundle
KNOWN_SECTIONS = ("faq", "competitions", "contacts", "schedule", "info")

# ---- Creator immutability policy ----
CREATOR_NAME = "Nicolas TL"
CREATOR_ID   = "2415674"
# Only 'description' may change; name & id are locked.

def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def save_yaml(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, sort_keys=False, allow_unicode=True)

def merge_dict_section(bundle, section_name, section_data):
    if section_name not in bundle:
        bundle[section_name] = {}
    if isinstance(section_data, dict):
        for k, v in section_data.items():
            if k in bundle[section_name]:
                print(f"[WARN] Duplicate key in '{section_name}': {k} (overwriting)")
            bundle[section_name][k] = v
    else:
        print(f"[WARN] Section '{section_name}' is not a dict; skipping merge.")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="data.index.yaml")
    ap.add_argument("--out", default="data.bundle.yaml")
    ap.add_argument("--json", default="data.bundle.json")
    args = ap.parse_args()

    if not os.path.exists(args.index):
        sys.exit(f"Index not found: {args.index}")

    index = load_yaml(args.index) or {}
    sources = index.get("sources", [])
    if not sources:
        sys.exit("No sources listed in index.")

    bundle = {
        "meta": {
            "bundle_built": datetime.datetime.now().isoformat(timespec="seconds"),
            "schema_version": index.get("schema_version", 1),
            "sources": [],
            "files": [],  # per-file meta copied here if present
        }
    }

    # Track any provided creator fields to enforce immutability
    seen_creator_entries = []  # list of tuples (path, name, id, description?)

    for item in sources:
        path = item["path"]
        required = bool(item.get("required", True))
        if not os.path.exists(path):
            if required:
                sys.exit(f"Required source missing: {path}")
            else:
                print(f"[INFO] Optional source missing, skipping: {path}")
                continue

        data = load_yaml(path) or {}
        bundle["meta"]["sources"].append({"path": path, "size_bytes": os.path.getsize(path)})

        # Record file-level meta into the bundle for provenance
        if "meta" in data:
            bundle["meta"]["files"].append({path: data["meta"]})

        # Merge known sections
        for section in KNOWN_SECTIONS:
            if section in data:
                # Special handling for 'info' so we can inspect creator fields
                if section == "info" and isinstance(data["info"], dict):
                    creator = (data["info"] or {}).get("creator")
                    if isinstance(creator, dict):
                        seen_creator_entries.append((
                            path,
                            creator.get("name"),
                            creator.get("id"),
                            creator.get("description"),
                        ))
                merge_dict_section(bundle, section, data[section])

    # ----- Enforce creator immutability -----
    # If any file attempts to set a different name or id, fail the build.
    for path, name, cid, _desc in seen_creator_entries:
        if name is not None and name != CREATOR_NAME:
            sys.exit(
                f"[ERROR] creator.name in {path} is immutable and must be '{CREATOR_NAME}', got '{name}'."
            )
        if cid is not None and str(cid) != CREATOR_ID:
            sys.exit(
                f"[ERROR] creator.id in {path} is immutable and must be '{CREATOR_ID}', got '{cid}'."
            )

    # Ensure bundle.info exists and lock name/id to constants
    info = bundle.setdefault("info", {})
    creator = info.setdefault("creator", {})
    # Preserve description from merged sources if present; lock name & id.
    # If no description was provided anywhere, leave it absent/None.
    if "description" not in creator:
        # try to take first provided description (if any)
        for _path, _name, _cid, desc in seen_creator_entries:
            if desc:
                creator["description"] = desc
                break
    creator["name"] = CREATOR_NAME
    creator["id"] = CREATOR_ID

    # ---- Lightweight validations ----
    problems = []

    # contacts.phone.number_e164 should start with '+'
    phone = (((bundle.get("contacts") or {}).get("phone")) or {})
    if isinstance(phone, dict) and "number_e164" in phone:
        if not str(phone["number_e164"]).startswith("+"):
            problems.append("contacts.phone.number_e164 must start with '+' (E.164 format)")

    # schedule.*.date should be YYYY-MM-DD strings
    schedule = bundle.get("schedule") or {}
    for sid, s in schedule.items():
        if "date" in s and not isinstance(s["date"], str):
            problems.append(f"schedule.{sid}.date must be string YYYY-MM-DD")

    if problems:
        print("VALIDATION WARNINGS:")
        for p in problems:
            print(" -", p)

    # Write outputs
    save_yaml(bundle, args.out)
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)

    print(f"Wrote {args.out} and {args.json}")

if __name__ == "__main__":
    main()
