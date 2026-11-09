"""위키백과(영문) 공용 함수: 문서 HTML 가져오기 + 표(table)를 행/열 격자로 풀기 (rowspan/colspan 처리).

위키백과 내용은 CC BY-SA 4.0 → 사이트에 출처 표기 필요 (source='wikipedia').
"""
import html
import json
import re
import urllib.parse
from html.parser import HTMLParser

from common import get_json

API = "https://en.wikipedia.org/w/api.php"


def page_html(title: str) -> tuple[str, int]:
    """(HTML, revid). revid 는 어느 판을 읽었는지 기록용."""
    q = urllib.parse.urlencode({"action": "parse", "format": "json", "prop": "text|revid",
                                "page": title, "redirects": 1, "disableeditsection": 1})
    d = get_json(f"{API}?{q}")
    if "error" in d:
        raise RuntimeError(f"위키백과 문서 오류 {title}: {d['error'].get('info')}")
    return d["parse"]["text"]["*"], d["parse"]["revid"]


def page_url(title: str) -> str:
    return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))


class _Tables(HTMLParser):
    """문서 안 모든 <table> → [{'heading': 직전 제목, 'rows': [[cell, ...], ...]}]. cell = {'text','th','links'}"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.stack = [], []
        self.heading, self._in_h, self._htext = "", False, ""
        self._skip = 0  # <sup>(각주), <style> 등 무시

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("h2", "h3", "h4"):
            self._in_h, self._htext = True, ""
        if tag in ("sup", "style", "script") or "display:none" in (a.get("style") or "").replace(" ", ""):
            self._skip += 1
            return
        if self._skip:
            if tag in ("sup", "style", "script"):
                self._skip += 1
            return
        if tag == "table":
            self.stack.append({"heading": self.heading, "rows": [], "cls": a.get("class", ""), "cell": None, "row": None})
        elif not self.stack:
            return
        t = self.stack[-1]
        if tag == "tr":
            t["row"] = []
        elif tag in ("td", "th") and t["row"] is not None:
            t["cell"] = {"text": "", "th": tag == "th", "links": [],
                         "rowspan": int(re.sub(r"\D", "", a.get("rowspan") or "1") or 1),
                         "colspan": int(re.sub(r"\D", "", a.get("colspan") or "1") or 1),
                         "style": a.get("style") or ""}
        elif tag == "br" and t["cell"] is not None:
            t["cell"]["text"] += "\n"
        elif tag == "a" and t["cell"] is not None and a.get("href", "").startswith("/wiki/"):
            t["cell"]["links"].append(urllib.parse.unquote(a["href"][6:]).replace("_", " "))

    def handle_endtag(self, tag):
        if tag in ("h2", "h3", "h4") and self._in_h:
            self._in_h, self.heading = False, self._htext.strip()
        if self._skip:
            if tag in ("sup", "style", "script"):
                self._skip -= 1
            return
        if not self.stack:
            return
        t = self.stack[-1]
        if tag in ("td", "th") and t["cell"] is not None:
            c = t["cell"]
            c["text"] = re.sub(r"[ \t\xa0]+", " ", c["text"]).strip()
            t["row"].append(c)
            t["cell"] = None
        elif tag == "tr" and t["row"] is not None:
            t["rows"].append(t["row"])
            t["row"] = None
        elif tag == "table":
            done = self.stack.pop()
            self.tables.append({"heading": done["heading"], "cls": done["cls"], "rows": _grid(done["rows"])})

    def handle_data(self, data):
        if self._in_h:
            self._htext += data
        if self._skip or not self.stack:
            return
        c = self.stack[-1]["cell"]
        if c is not None:
            c["text"] += data


def _grid(rows):
    """rowspan/colspan 을 펼쳐 모든 행이 같은 열 위치를 갖게 함."""
    out, pending = [], {}  # pending[col] = [cell, 남은 행 수]
    for row in rows:
        line, col, it = [], 0, iter(row)
        cells = list(it)
        i = 0
        while i < len(cells) or any(c >= col for c in pending):
            if col in pending:
                cell, left = pending[col]
                line.append(cell)
                pending[col][1] -= 1
                if pending[col][1] == 0:
                    del pending[col]
                col += 1
                continue
            if i >= len(cells):
                break
            cell = cells[i]
            i += 1
            for _ in range(cell["colspan"]):
                line.append(cell)
                if cell["rowspan"] > 1:
                    pending[col] = [cell, cell["rowspan"] - 1]
                col += 1
        out.append(line)
    return out


def tables(page: str) -> list[dict]:
    p = _Tables()
    p.feed(page)
    return p.tables


def clean(text: str) -> str:
    return html.unescape(re.sub(r"\[[^\]]*\]", "", text or "")).strip()


def to_int(text: str) -> int | None:
    m = re.search(r"-?\d+", (text or "").replace(",", "").replace("−", "-"))
    return int(m.group()) if m else None
