import React, { useState, useEffect, useRef } from "react";
import { api } from "../lib/api";

export default function MedicineAutocomplete({ value, onChange, onSelect, testid = "medicine-input" }) {
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const wrapRef = useRef(null);

  useEffect(() => {
    if (!value || value.trim().length < 1) {
      setSuggestions([]);
      setOpen(false);
      return;
    }
    let cancel = false;
    const t = setTimeout(async () => {
      try {
        const { data } = await api.get(`/medicines/suggest`, { params: { q: value } });
        if (!cancel) {
          setSuggestions(data);
          setOpen(true);
          setHighlight(0);
        }
      } catch (err) {
        console.error("Medicine suggest failed:", err);
      }
    }, 180);
    return () => { cancel = true; clearTimeout(t); };
  }, [value]);

  useEffect(() => {
    const onClickOutside = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const pick = (s) => {
    onSelect(s);
    setOpen(false);
  };

  const handleKey = (e) => {
    if (!open || suggestions.length === 0) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setHighlight((h) => Math.min(h + 1, suggestions.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHighlight((h) => Math.max(h - 1, 0)); }
    else if (e.key === "Enter" && suggestions[highlight]) {
      e.preventDefault();
      pick(suggestions[highlight]);
    } else if (e.key === "Escape") setOpen(false);
  };

  return (
    <div ref={wrapRef} className="relative">
      <input
        data-testid={testid}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => value && setOpen(suggestions.length > 0)}
        onKeyDown={handleKey}
        placeholder="Start typing a medicine or company…"
        className="w-full px-5 py-4 text-lg rounded-2xl bg-white border border-[#E5E1DB] focus:outline-none focus:ring-2 focus:ring-[#4A5D4E]/40 focus:border-[#4A5D4E]"
        autoComplete="off"
      />
      {open && suggestions.length > 0 && (
        <ul
          data-testid="suggestion-list"
          className="absolute z-20 left-0 right-0 mt-2 max-h-80 overflow-y-auto rounded-2xl bg-white border border-[#E5E1DB] shadow-[0_10px_30px_rgba(74,93,78,0.12)]"
        >
          {suggestions.map((s, i) => (
            <li
              key={s.id}
              data-testid={`suggestion-${s.id}`}
              className={`px-5 py-3 cursor-pointer flex items-baseline justify-between gap-4 border-b border-[#F2EFEB] last:border-b-0 ${
                i === highlight ? "bg-[#F2EFEB]" : "hover:bg-[#F9F8F6]"
              }`}
              onMouseDown={(e) => { e.preventDefault(); pick(s); }}
              onMouseEnter={() => setHighlight(i)}
            >
              <div>
                <div className="font-medium text-[#2C312E]">{s.name}</div>
                {s.company && <div className="text-xs text-[#6B726C] mt-0.5">{s.company}</div>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
