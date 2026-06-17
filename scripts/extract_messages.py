"""Extract translatable strings from templates and Python source.

This is a minimal stand-in for ``django-admin makemessages``, which requires
GNU gettext tools (xgettext/msguniq/msgmerge) that are not available in this
environment. It walks the project tree looking for:

- ``{% translate "..." %}`` / ``{% trans "..." %}``
- ``{% blocktranslate %}...{% endblocktranslate %}`` (and ``blocktrans``),
  including ``{% plural %}`` sections
- ``gettext_lazy("...")``, ``gettext("...")``, ``_("...")``, ``ngettext(...)``

and writes a sorted list of unique msgids (and msgid/msgid_plural pairs) to
stdout as a JSON document, for use when hand-building the .po catalogs.
"""

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SKIP_DIRS = {".venv", "node_modules", "locale", "__pycache__", ".git", "staticfiles", "scripts"}

TEMPLATE_EXTS = {".html", ".txt"}
PY_EXT = ".py"

# {% translate "..." %} or {% trans "..." %}
RE_TRANS = re.compile(r"{%\s*(?:translate|trans)\s+(['\"])(.*?)\1(?:\s+[^%]*)?%}")

# {% blocktranslate ... %} ... {% endblocktranslate %} (also blocktrans)
RE_BLOCKTRANS = re.compile(
    r"{%\s*(blocktranslate|blocktrans)([^%]*)%}(.*?){%\s*end\1\s*%}",
    re.DOTALL,
)

# gettext_lazy("...") / gettext("...") / _("...") / pgettext("ctx", "...")
RE_PY_SIMPLE = re.compile(
    r"(?:gettext_lazy|gettext|_)\(\s*(['\"])((?:[^\\]|\\.)*?)\1\s*\)"
)

# ngettext("singular", "plural", n)
RE_PY_NGETTEXT = re.compile(
    r"ngettext(?:_lazy)?\(\s*(['\"])((?:[^\\]|\\.)*?)\1\s*,\s*(['\"])((?:[^\\]|\\.)*?)\3\s*,"
)


def iter_files():
    for path in BASE_DIR.rglob("*"):
        if path.is_dir():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix in TEMPLATE_EXTS or path.suffix == PY_EXT:
            yield path


def normalize_block(text):
    """Collapse internal whitespace/newlines the way blocktranslate would."""
    return " ".join(text.split())


def extract_from_template(text):
    singles = set()
    plurals = set()

    for m in RE_TRANS.finditer(text):
        singles.add(m.group(2))

    for m in RE_BLOCKTRANS.finditer(text):
        body = m.group(3)
        if "{% plural %}" in body or "{%plural%}" in body:
            parts = re.split(r"{%\s*plural\s*%}", body)
            singular = normalize_block(parts[0])
            plural = normalize_block(parts[1]) if len(parts) > 1 else singular
            plurals.add((singular, plural))
        else:
            singles.add(normalize_block(body))

    return singles, plurals


def extract_from_python(text):
    singles = set()
    plurals = set()

    for m in RE_PY_NGETTEXT.finditer(text):
        plurals.add((m.group(2), m.group(4)))

    # Remove ngettext calls before scanning for simple ones to avoid
    # accidentally matching the inner strings as separate singles.
    text_wo_ngettext = RE_PY_NGETTEXT.sub("", text)
    for m in RE_PY_SIMPLE.finditer(text_wo_ngettext):
        singles.add(m.group(2))

    return singles, plurals


def main():
    all_singles = set()
    all_plurals = set()

    for path in iter_files():
        text = path.read_text(encoding="utf-8")
        if path.suffix == PY_EXT:
            s, p = extract_from_python(text)
        else:
            s, p = extract_from_template(text)
        all_singles |= s
        all_plurals |= p

    # A msgid that also appears as a plural singular shouldn't be duplicated
    # as a separate non-plural entry.
    plural_singulars = {s for s, _ in all_plurals}
    all_singles -= plural_singulars

    result = {
        "singles": sorted(all_singles),
        "plurals": sorted(all_plurals),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
