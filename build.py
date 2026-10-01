"""Build the website: fill the page template and generate the publication lists.

    python build.py

Reads the shared bibliography ../CV/publications.bib (the CV uses the same file), the
page bodies in content/, and templates/base.html, and writes the pages to this folder.
It also copies ../CV/cv_public.pdf to cv.pdf when that file exists. No dependencies.
"""
from __future__ import annotations

import html
import pathlib
import re
import shutil

HERE = pathlib.Path(__file__).resolve().parent
BIB = HERE.parent / "CV" / "publications.bib"
CV_PDF = HERE.parent / "CV" / "cv_public.pdf"
ME = ("Magassouba", ("Aly", "A."))

PAGES = {  # output file: (navigation key, title, content file)
    "index.html": ("about", "Aly Magassouba", "index.html"),
    "research.html": ("research", "Research | Aly Magassouba", "research.html"),
    "publications.html": ("publications", "Publications | Aly Magassouba", "publications.html"),
    "teaching.html": ("teaching", "Teaching | Aly Magassouba", "teaching.html"),
}

GROUPS = [("journal", "Journal articles"), ("conference", "Conference papers"),
          ("workshop", "Workshop papers and preprints"), ("other", "Other publications"),
          ("thesis", "Thesis")]

THEMES = {"communicate": "Communicating with humans",
          "perceive": "Perceiving and understanding the world",
          "physical": "Physically interacting with the world"}

# The home page's selected publications, in this order.
SELECTED = ["fujii2026phypush", "deflesselle2026maneuvernet", "daniel2024multi",
            "magassouba2021crossmap", "magassouba2018multimodal", "magassouba2018aural"]


# ---------------------------------------------------------------- BibTeX

def parse_bib(text: str) -> list[dict]:
    """Entries of a BibTeX file as dicts (fields lower-cased; `type`, `key`).

    Lines starting with % are comments. Field values may be braced (nested) or quoted.
    """
    text = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("%"))
    entries, i = [], 0
    while True:
        m = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,").search(text, i)
        if not m:
            return entries
        entry = {"type": m.group(1).lower(), "key": m.group(2)}
        i = m.end()
        while True:
            f = re.compile(r"\s*(\w[\w+-]*)\s*=\s*").match(text, i)
            if not f:
                break
            name, i = f.group(1).lower(), f.end()
            if text[i] == "{":
                depth, j = 0, i
                while True:
                    depth += {"{": 1, "}": -1}.get(text[j], 0)
                    if depth == 0:
                        break
                    j += 1
                value, i = text[i + 1:j], j + 1
            elif text[i] == '"':
                j = text.index('"', i + 1)
                value, i = text[i + 1:j], j + 1
            else:
                v = re.compile(r"[^,}\s]+").match(text, i)
                value, i = v.group(0), v.end()
            entry[name] = " ".join(value.split())
            c = re.compile(r"\s*,?").match(text, i)
            i = c.end()
        entries.append(entry)
        i = text.index("}", i) + 1


ACCENTS = {"'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303",
           "c": "\u0327"}


def latex_to_text(s: str) -> str:
    """Convert the LaTeX used in the bibliography to plain Unicode text."""
    import unicodedata

    def accent(m):
        return unicodedata.normalize("NFC", m.group(2) + ACCENTS[m.group(1)])

    s = re.sub(r"\{\\([`'^\"~c])\s*\{?(\w)\}?\}", accent, s)
    s = re.sub(r"\\([`'^\"~])\{?(\w)\}?", accent, s)
    s = re.sub(r"\\c\{(\w)\}", lambda m: unicodedata.normalize("NFC", m.group(1) + "\u0327"), s)
    s = s.replace("---", "\u2014").replace("--", "\u2013").replace("\\&", "&")
    s = s.replace("~", "\u00a0").replace("\\", "")
    return s.replace("{", "").replace("}", "")


def person(name: str) -> str:
    name = latex_to_text(name)
    if "," in name:
        last, first = (p.strip() for p in name.split(",", 1))
    else:
        parts = name.split()
        first, last = " ".join(parts[:-1]), parts[-1]
    full = html.escape(f"{first} {last}".strip())
    if last == ME[0] and first in ME[1]:
        return f'<span class="me">{full}</span>'
    return full


def authors(field: str) -> str:
    names = [person(a) for a in re.split(r"\s+and\s+", field)]
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + ", and " + names[-1]


def venue(e: dict) -> str:
    t = e["type"]
    if t == "article":
        v = f"<em>{html.escape(latex_to_text(e.get('journal', '')))}</em>"
        if e.get("volume"):
            v += f" {e['volume']}" + (f"({e['number']})" if e.get("number") else "")
        if e.get("pages"):
            v += f", {latex_to_text(e['pages'])}"
        return v
    if t == "phdthesis":
        return f"PhD thesis, {html.escape(latex_to_text(e.get('school', '')))}"
    v = f"<em>{html.escape(latex_to_text(e.get('booktitle', '')))}</em>"
    if e.get("pages"):
        v += f", {latex_to_text(e['pages'])}"
    return v


def links(e: dict) -> str:
    out = []
    if e.get("doi"):
        out.append(f'<a href="https://doi.org/{html.escape(e["doi"])}">DOI</a>')
    if e.get("eprint") and e.get("eprinttype", "").lower() == "arxiv":
        out.append(f'<a href="https://arxiv.org/abs/{html.escape(e["eprint"])}">arXiv</a>')
    if e.get("url"):
        out.append(f'<a href="{html.escape(e["url"])}">Paper</a>')
    return " ".join(out)


def keywords(e: dict) -> list[str]:
    return [k.strip() for k in e.get("keywords", "").split(",") if k.strip()]


def render_entry(e: dict, show_themes: bool = False, thumb: bool = False) -> str:
    image = HERE / "assets" / "papers" / f'{e["key"]}.jpg'
    if thumb and image.exists():
        first = f'<img class="thumb" src="assets/papers/{image.name}" alt="" loading="lazy">'
        cls = "pub has-thumb"
    else:
        first = f'<span class="year">{e.get("year", "")}</span>'
        cls = "pub"
    status = ' <span class="tag">to appear</span>' if e.get("pubstate") == "forthcoming" else ""
    note = f' <span class="note">{html.escape(latex_to_text(e["note"]))}</span>' if e.get("note") else ""
    themes = ""
    if show_themes:
        labels = [f'<a class="theme-tag" href="research.html#{k}">{THEMES[k]}</a>'
                  for k in keywords(e) if k in THEMES]
        themes = f'<br><span class="themes">{" ".join(labels)}</span>' if labels else ""
    return (f'<li class="{cls}">{first}'
            f'<div><span class="title">{html.escape(latex_to_text(e["title"]))}</span>{status}<br>'
            f'<span class="authors">{authors(e.get("author", ""))}</span><br>'
            f'<span class="venue">{venue(e)}, {e.get("year", "")}.</span>{note}'
            f' <span class="links">{links(e)}</span>{themes}</div></li>')


def by_year(entries):
    return sorted(entries, key=lambda e: (-int(e.get("year", 0)), e.get("title", "")))


def publications_html(entries) -> str:
    parts = []
    for key, title in GROUPS:
        group = by_year([e for e in entries if key in keywords(e)])
        if group:
            parts.append(f'<h2 id="{key}">{title}</h2>\n<ol class="pubs">\n'
                         + "\n".join(render_entry(e, show_themes=True) for e in group) + "\n</ol>")
    return "\n".join(parts)


def selected_html(entries) -> str:
    by_key = {e["key"]: e for e in entries}
    missing = [k for k in SELECTED if k not in by_key]
    if missing:
        raise SystemExit(f"selected publications not in the bibliography: {missing}")
    return ('<ol class="pubs compact">\n'
            + "\n".join(render_entry(by_key[k], thumb=True) for k in SELECTED) + "\n</ol>")


def theme_html(entries, theme: str) -> str:
    group = by_year([e for e in entries if theme in keywords(e)])
    return ('<details class="theme-pubs"><summary>Publications '
            f'({len(group)})</summary>\n<ol class="pubs compact">\n'
            + "\n".join(render_entry(e) for e in group) + "\n</ol></details>")


# ---------------------------------------------------------------- pages

def main() -> None:
    entries = parse_bib(BIB.read_text(encoding="utf-8"))
    base = (HERE / "templates" / "base.html").read_text(encoding="utf-8")
    for out, (nav, title, src) in PAGES.items():
        body = (HERE / "content" / src).read_text(encoding="utf-8")
        body = body.replace("<!-- PUBLICATIONS -->", publications_html(entries))
        body = body.replace("<!-- SELECTED -->", selected_html(entries))
        for theme in THEMES:
            body = body.replace(f"<!-- THEME:{theme} -->", theme_html(entries, theme))
        body = body.replace("<!-- COUNT -->", str(len(entries)))
        page = base.replace("{{title}}", title).replace("{{content}}", body)
        page = page.replace(f'data-nav="{nav}"', f'data-nav="{nav}" aria-current="page"')
        (HERE / out).write_text(page, encoding="utf-8", newline="\n")
        print(f"wrote {out}")
    if CV_PDF.exists():
        shutil.copy2(CV_PDF, HERE / "cv.pdf")
        print("copied cv.pdf")
    print(f"{len(entries)} publications")


if __name__ == "__main__":
    main()
