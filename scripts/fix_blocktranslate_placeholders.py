"""Fix blocktranslate msgids/translations to use %(name)s placeholders.

Django's {% blocktranslate %} tag converts {{ var }} references into
%(var)s placeholders in the actual msgid passed to gettext. The extraction
script captured the raw template text (with {{ var }}), so any catalog
entry containing "{{ name }}" does not match the runtime msgid and falls
back to the untranslated English source. This script rewrites those
entries (and their de/fr/it translations) to use %(var)s placeholders,
both in scripts/i18n_chunks/*.json and the existing locale/*/django.po
sources, before catalogs are rebuilt.
"""

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CHUNKS_DIR = BASE_DIR / "scripts" / "i18n_chunks"

PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def convert(text):
    return PLACEHOLDER_RE.sub(r"%(\1)s", text)


def fix_singles(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    new_data = {}
    changed = False
    for msgid, translations in data.items():
        if "{{" in msgid:
            new_msgid = convert(msgid)
            new_translations = {lang: convert(text) for lang, text in translations.items()}
            new_data[new_msgid] = new_translations
            changed = True
        else:
            new_data[msgid] = translations
    if changed:
        path.write_text(json.dumps(new_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def fix_plurals(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    for entry in data:
        for key in ("singular", "plural"):
            if "{{" in entry[key]:
                entry[key] = convert(entry[key])
                changed = True
        for lang in ("de", "fr", "it"):
            entry[lang] = [convert(t) for t in entry[lang]]
    if changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def main():
    for f in sorted(CHUNKS_DIR.glob("chunk*.json")):
        if fix_singles(f):
            print(f"fixed {f}")
    if fix_plurals(CHUNKS_DIR / "plurals.json"):
        print(f"fixed {CHUNKS_DIR / 'plurals.json'}")


if __name__ == "__main__":
    main()
