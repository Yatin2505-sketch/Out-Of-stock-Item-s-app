import React, { useEffect, useState, useCallback } from "react";
import AppShell from "../components/AppShell";
import MedicineAutocomplete from "../components/MedicineAutocomplete";
import { api, formatApiError } from "../lib/api";
import { toast } from "sonner";
import { Check, Trash2, PackageOpen } from "lucide-react";

export default function EmployeeHome() {
  const [name, setName] = useState("");
  const [selected, setSelected] = useState(null);
  const [quantity, setQuantity] = useState("");
  const [showQtyDialog, setShowQtyDialog] = useState(false);
  const [logs, setLogs] = useState([]);
  const [submitting, setSubmitting] = useState(false);

  const loadLogs = useCallback(async () => {
    try {
      const { data } = await api.get("/logs");
      setLogs(data);
    } catch (err) {
      console.error("Failed to load logs:", err);
      toast.error("Couldn't load today's notes");
    }
  }, []);

  useEffect(() => { loadLogs(); }, [loadLogs]);

  const handleSelect = (m) => {
    setSelected(m);
    setName(m.name);
    setQuantity("");
    setShowQtyDialog(true);
  };

  const handleAddNew = () => {
    if (!name.trim()) return;
    setSelected(null);
    setQuantity("");
    setShowQtyDialog(true);
  };

  const submit = async () => {
    setSubmitting(true);
    try {
      await api.post("/logs", {
        medicine_id: selected?.id || null,
        medicine_name: selected?.name || name,
        quantity: quantity.trim(),
      });
      toast.success("Noted down — thank you.");
      setName(""); setSelected(null); setQuantity(""); setShowQtyDialog(false);
      loadLogs();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) || "Failed to save");
    } finally { setSubmitting(false); }
  };

  const remove = async (id) => {
    try {
      await api.delete(`/logs/${id}`);
      loadLogs();
    } catch (err) {
      console.error("Delete log failed:", err);
      toast.error("Couldn't delete the note");
    }
  };

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto px-6 py-14">
        <div className="mb-10">
          <div className="text-xs uppercase tracking-[0.25em] text-[#6B726C]">Today · {new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}</div>
          <h1 className="font-serif text-5xl mt-2 text-[#2C312E] leading-none">Note a medicine that's running low</h1>
          <p className="mt-4 text-[#6B726C]">Type the name — we'll suggest matches. Then just enter what's left on the shelf.</p>
        </div>

        <div className="space-y-4">
          <MedicineAutocomplete
            value={name}
            onChange={setName}
            onSelect={handleSelect}
            testid="employee-medicine-input"
          />
          {name && !showQtyDialog && (
            <button
              data-testid="add-new-medicine-btn"
              onClick={handleAddNew}
              className="pill-btn px-6 py-3 bg-[#4A5D4E] text-white hover:bg-[#3D4D40] transition-colors text-sm"
            >
              Continue with "{name}"
            </button>
          )}
        </div>

        {/* Today's list */}
        <div className="mt-16">
          <div className="flex items-baseline justify-between mb-4">
            <h2 className="font-serif text-2xl text-[#2C312E]">Your notes today</h2>
            <span className="text-sm text-[#6B726C]">{logs.length} item{logs.length !== 1 ? "s" : ""}</span>
          </div>
          {logs.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-[#E5E1DB] p-10 text-center bg-white/50">
              <PackageOpen className="mx-auto text-[#6B726C] mb-3" size={28} />
              <p className="text-[#6B726C]">Nothing noted yet. Start by typing above.</p>
            </div>
          ) : (
            <ul className="space-y-2" data-testid="employee-logs">
              {logs.map((l) => (
                <li key={l.id} data-testid={`log-${l.id}`} className="flex items-center justify-between bg-white border border-[#E5E1DB] rounded-2xl px-5 py-4">
                  <div className="min-w-0">
                    <div className="font-medium text-[#2C312E] truncate">{l.medicine_name}</div>
                    <div className="text-xs text-[#6B726C] mt-0.5">Qty left: <span className="text-[#2C312E]">{l.quantity || "—"}</span></div>
                  </div>
                  <button
                    data-testid={`delete-log-${l.id}`}
                    onClick={() => remove(l.id)}
                    className="p-2 rounded-full text-[#6B726C] hover:text-[#B04A3A] hover:bg-[#F7E9E4] transition-colors"
                  >
                    <Trash2 size={16} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Quantity dialog */}
      {showQtyDialog && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-[#2C312E]/40 backdrop-blur-sm px-4" data-testid="quantity-dialog">
          <div className="bg-white rounded-3xl border border-[#E5E1DB] max-w-md w-full p-8 shadow-[0_30px_60px_rgba(0,0,0,0.15)]">
            <div className="text-xs uppercase tracking-[0.25em] text-[#6B726C]">Quantity left</div>
            <h3 className="font-serif text-3xl mt-1 text-[#2C312E]">{selected?.name || name}</h3>
            {selected?.company && <div className="text-sm text-[#6B726C] mt-1">{selected.company}</div>}
            <div className="mt-6">
              <input
                data-testid="quantity-input"
                autoFocus
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                placeholder="e.g. 3 strips, 1 bottle, none"
                className="w-full px-4 py-3 rounded-xl bg-white border border-[#E5E1DB] focus:outline-none focus:ring-2 focus:ring-[#4A5D4E]/40 focus:border-[#4A5D4E]"
              />
            </div>
            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                data-testid="cancel-quantity-btn"
                onClick={() => setShowQtyDialog(false)}
                className="pill-btn px-5 py-2.5 border border-[#E5E1DB] text-[#2C312E] hover:bg-[#F2EFEB]"
              >
                Cancel
              </button>
              <button
                data-testid="submit-quantity-btn"
                onClick={submit}
                disabled={submitting}
                className="pill-btn inline-flex items-center gap-2 px-6 py-2.5 bg-[#4A5D4E] text-white hover:bg-[#3D4D40] disabled:opacity-50"
              >
                <Check size={16} /> Save
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
