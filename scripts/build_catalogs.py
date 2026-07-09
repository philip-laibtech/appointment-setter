"""Build django.po / django.mo catalogs for de, fr, it, en.

GNU gettext tools (msgfmt/xgettext/msguniq) are not available in this
environment, so this script uses the pure-Python ``babel`` package (added to
requirements.txt) to write and compile the catalogs instead of
``django-admin makemessages``/``compilemessages``.

Source strings are English (LANGUAGE_CODE for the project is "de", but all
msgids in the source code/templates are written in English). Translations for
de/fr/it are stored in scripts/i18n_chunks/*.json. The "en" catalog is left
with empty msgstrs so gettext falls back to the (English) msgid.
"""

import json
from pathlib import Path

from babel.messages.catalog import Catalog, Message
from babel.messages.mofile import write_mo
from babel.messages.pofile import write_po

BASE_DIR = Path(__file__).resolve().parent.parent
CHUNKS_DIR = BASE_DIR / "scripts" / "i18n_chunks"
LOCALE_DIR = BASE_DIR / "locale"

PLURAL_RULES = {
    "de": "nplurals=2; plural=(n != 1);",
    "fr": "nplurals=2; plural=(n > 1);",
    "it": "nplurals=2; plural=(n != 1);",
    "en": "nplurals=2; plural=(n != 1);",
}


def load_singles():
    merged = {}
    for f in sorted(CHUNKS_DIR.glob("chunk*.json")):
        merged.update(json.loads(f.read_text(encoding="utf-8")))
    return merged


def load_plurals():
    return json.loads((CHUNKS_DIR / "plurals.json").read_text(encoding="utf-8"))


def build_catalog(locale, singles, plurals):
    catalog = Catalog(
        locale=locale,
        project="Terminklick",
        charset="utf-8",
    )
    catalog._header_comment = ""
    catalog.mime_headers = catalog.mime_headers + [
        ("Plural-Forms", PLURAL_RULES[locale])
    ]

    for msgid, translations in singles.items():
        msgstr = "" if locale == "en" else translations.get(locale, "")
        catalog.add(msgid, string=msgstr)

    for entry in plurals:
        msgid = (entry["singular"], entry["plural"])
        if locale == "en":
            msgstr = ("", "")
        else:
            msgstr = tuple(entry[locale])
        catalog.add(msgid, string=msgstr)

    return catalog


def main():
    singles = load_singles()
    plurals = load_plurals()

    for locale in ("de", "fr", "it", "en"):
        out_dir = LOCALE_DIR / locale / "LC_MESSAGES"
        out_dir.mkdir(parents=True, exist_ok=True)

        catalog = build_catalog(locale, singles, plurals)

        po_path = out_dir / "django.po"
        with open(po_path, "wb") as f:
            write_po(f, catalog, width=200, omit_header=False)

        # Babel marks the header entry as fuzzy by default; strip that so
        # the catalog doesn't look untranslated/auto-generated to tooling.
        po_text = po_path.read_text(encoding="utf-8")
        po_text = po_text.replace("#, fuzzy\n", "", 1)
        po_path.write_text(po_text, encoding="utf-8")

        mo_path = out_dir / "django.mo"
        with open(mo_path, "wb") as f:
            write_mo(f, catalog)

        print(f"{locale}: wrote {po_path} and {mo_path} "
              f"({len(singles)} singular + {len(plurals)} plural messages)")


if __name__ == "__main__":
    main()
