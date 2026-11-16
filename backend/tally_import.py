"""Read purchase bills exported from Tally Prime (XML) and work out which
stock items were bought from which party (supplier).

How the user exports (Tally Prime):
  Display More Reports > Account Books > Purchase Register > pick the period
  > Alt+E (Export) > File Format: XML (Data Interchange) > Send.
A Day Book export works too; only purchase vouchers are used.

Tally XML quirks handled here:
  * files are often UTF-16 (with BOM) or UTF-8, sometimes without BOM
  * tags with undeclared prefixes such as <UDF:FOO.LIST> (invalid XML namespaces)
  * control-character references like &#4; that XML 1.0 forbids
"""
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Iterator, List, Optional

_PREFIX_TAG = re.compile(rb"<(/?)([A-Za-z_][\w.-]*):")
_CHAR_REF = re.compile(rb"&#(x[0-9a-fA-F]+|[0-9]+);")
_BAD_RAW = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _drop_bad_ref(m: "re.Match") -> bytes:
    ref = m.group(1)
    code = int(ref[1:], 16) if ref[:1] in (b"x", b"X") else int(ref)
    # XML 1.0 forbids control characters other than tab, newline and carriage return
    return b"" if code < 32 and code not in (9, 10, 13) else m.group(0)


@dataclass
class PurchaseBill:
    key: str
    date: str  # YYYY-MM-DD or ""
    party: str
    items: List[str] = field(default_factory=list)


def _to_utf8(raw: bytes) -> bytes:
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16")
    elif raw.startswith(b"\xef\xbb\xbf"):
        text = raw[3:].decode("utf-8", errors="replace")
    elif len(raw) > 1 and raw[1:2] == b"\x00":  # UTF-16 LE without BOM
        text = raw.decode("utf-16-le", errors="replace")
    elif raw[:1] == b"\x00":  # UTF-16 BE without BOM
        text = raw.decode("utf-16-be", errors="replace")
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("cp1252", errors="replace")
    # The XML declaration may claim UTF-16; we hand bytes to the parser as UTF-8.
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text, count=1)
    return text.encode("utf-8")


def _clean(raw: bytes) -> bytes:
    data = _to_utf8(raw)
    data = _PREFIX_TAG.sub(rb"<\1\2_", data)
    data = _CHAR_REF.sub(_drop_bad_ref, data)
    data = _BAD_RAW.sub(b"", data)
    return data


def _text(el: Optional[ET.Element]) -> str:
    return (el.text or "").strip() if el is not None else ""


def _is_purchase(v: ET.Element) -> bool:
    vtype = (v.get("VCHTYPE") or _text(v.find("VOUCHERTYPENAME"))).lower()
    if "purchase" not in vtype:
        return False
    if "order" in vtype or "return" in vtype:
        return False
    for flag in ("ISCANCELLED", "ISOPTIONAL", "ISDELETED"):
        if _text(v.find(flag)).lower() == "yes":
            return False
    return True


def _party(v: ET.Element) -> str:
    for tag in ("PARTYLEDGERNAME", "PARTYNAME", "BASICBUYERNAME"):
        name = _text(v.find(tag))
        if name:
            return name
    for le in list(v.iter("LEDGERENTRIES.LIST")) + list(v.iter("ALLLEDGERENTRIES.LIST")):
        if _text(le.find("ISPARTYLEDGER")).lower() == "yes":
            name = _text(le.find("LEDGERNAME"))
            if name:
                return name
    return ""


def _date(v: ET.Element) -> str:
    d = _text(v.find("DATE"))
    if len(d) == 8 and d.isdigit():
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return ""


def parse_purchase_bills(raw: bytes) -> Iterator[PurchaseBill]:
    """Yield one PurchaseBill per purchase voucher in a Tally XML export."""
    data = _clean(raw)
    for _event, el in ET.iterparse(io.BytesIO(data), events=("end",)):
        if el.tag != "VOUCHER":
            continue
        if _is_purchase(el):
            party = _party(el)
            items = []
            for si in el.iter("STOCKITEMNAME"):
                name = _text(si)
                if name and name not in items:
                    items.append(name)
            if party and items:
                guid = _text(el.find("GUID")) or el.get("REMOTEID") or ""
                date = _date(el)
                number = _text(el.find("VOUCHERNUMBER"))
                key = guid or f"{date}|{number}|{party}"
                yield PurchaseBill(key=key, date=date, party=party, items=items)
        el.clear()  # keep memory low on big files
