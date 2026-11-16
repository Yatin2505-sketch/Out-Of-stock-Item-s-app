import React, { useEffect, useState, useCallback } from "react";
import AppShell from "../components/AppShell";
import { api, formatApiError } from "../lib/api";
import { toast } from "sonner";
import { Plus, Search, Upload, ClipboardPaste, Pencil, Trash2, X, FileUp } from "lucide-react";

export default function MedicineDatabase() {
  const [medicines, setMedicines] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [q, setQ] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [showPaste, setShowPaste] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ name: "", company: "", default_supplier_id: "" });
  const [pasteText, setPasteText] = useState("");
  const [showTally, setShowTally] = useState(false);
  const [tallyFile, setTallyFile] = useState(null);
  const [tallyUpdateDefaults, setTallyUpdateDefaults] = useState(false);
  const [tallyBusy, setTallyBusy] = useState(false);
  const [tallyResult, setTallyResult] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [m, s] = await Promise.all([
        api.get("/medicines", { params: { q: q || undefined } }),
        api.get("/suppliers"),
      ]);
      setMedicines(m.data); setSuppliers(s.data);
    } finally { setLoading(false); }
  }, [q]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  const openNew = () => { setEditing(null); setForm({ name: "", company: "", default_supplier_id: "" }); setShowForm(true); };
  const openEdit = (m) => { setEditing(m); setForm({ name: m.name, company: m.company || "", default_supplier_id: m.default_supplier_id || "" }); setShowForm(true); };

  const submit = async (e) => {
    e.preventDefault();
    const body = { ...form, default_supplier_id: form.default_supplier_id || null };
    try {
      if (editing) await api.put(`/medicines/${editing.id}`, body);
      else await api.post("/medicines", body);
      toast.success(editing ? "Updated" : "Added");
      setShowForm(false); load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this medicine?")) return;
    try { await api.delete(`/medicines/${id}`); load(); } catch { toast.error("Failed"); }
  };

  const uploadFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const isXlsx = file.name.toLowerCase().endsWith(".xlsx") || file.name.toLowerCase().endsWith(".xls");
    const fd = new FormData(); fd.append("file", file);
    try {
      const { data } = await api.post(isXlsx ? "/medicines/import/xlsx" : "/medicines/import/csv", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`Imported: ${data.added} added, ${data.updated} updated`);
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    finally { e.target.value = ""; }
  };

  const openTally = () => { setTallyFile(null); setTallyResult(null); setTallyUpdateDefaults(false); setShowTally(true); };

  const submitTally = async () => {
    if (!tallyFile) return;
    const fd = new FormData();
    fd.append("file", tallyFile);
    fd.append("update_defaults", tallyUpdateDefaults ? "true" : "false");
    setTallyBusy(true);
    try {
      const { data } = await api.post("/medicines/import/tally", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setTallyResult(data);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setTallyBusy(false); }
  };

  const submitPaste = async () => {
    try {
      const { data } = await api.post("/medicines/import/paste", { text: pasteText, delimiter: "," });
      toast.success(`Imported: ${data.added} added, ${data.updated} updated`);
      setShowPaste(false); setPasteText(""); load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  return (
    <AppShell>
      <div className="px-4 md:px-10 py-8 max-w-6xl">
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-8">
          <div>
            <div className="text-xs uppercase tracking-[0.25em] text-[#6B726C]">Records</div>
            <h1 className="font-serif text-4xl md:text-5xl mt-1 text-[#2C312E]">Medicine database</h1>
            <p className="mt-2 text-[#6B726C] text-sm">The living library imported from Tally, plus anything added along the way.</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              data-testid="import-tally-btn"
              onClick={openTally}
              className="pill-btn inline-flex items-center gap-2 px-5 py-2.5 border border-[#4A5D4E] bg-white text-sm text-[#4A5D4E] hover:bg-[#F2EFEB]"
            >
              <FileUp size={16} /> Import from Tally
            </button>
            <label className="pill-btn inline-flex items-center gap-2 px-5 py-2.5 border border-[#E5E1DB] bg-white text-sm hover:bg-[#F2EFEB] cursor-pointer" data-testid="import-file-label">
              <Upload size={16} /> Import CSV/Excel
              <input data-testid="import-file-input" type="file" accept=".csv,.xlsx,.xls" onChange={uploadFile} className="hidden" />
            </label>
            <button
              data-testid="import-paste-btn"
              onClick={() => setShowPaste(true)}
              className="pill-btn inline-flex items-center gap-2 px-5 py-2.5 border border-[#E5E1DB] bg-white text-sm hover:bg-[#F2EFEB]"
            >
              <ClipboardPaste size={16} /> Paste rows
            </button>
            <button
              data-testid="add-medicine-btn"
              onClick={openNew}
              className="pill-btn inline-flex items-center gap-2 px-5 py-2.5 bg-[#4A5D4E] text-white text-sm hover:bg-[#3D4D40]"
            >
              <Plus size={16} /> Add medicine
            </button>
          </div>
        </div>

        <div className="relative max-w-md mb-6">
          <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#6B726C]" />
          <input
            data-testid="search-medicines"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by medicine or company…"
            className="w-full pl-11 pr-4 py-3 rounded-full bg-white border border-[#E5E1DB] focus:outline-none focus:ring-2 focus:ring-[#4A5D4E]/40"
          />
        </div>

        <div className="bg-white rounded-2xl border border-[#E5E1DB] overflow-hidden">
          <table className="w-full">
            <thead className="bg-[#F2EFEB] text-left">
              <tr>
                <th className="px-6 py-3 text-xs uppercase tracking-wider text-[#6B726C] font-medium">Medicine</th>
                <th className="px-6 py-3 text-xs uppercase tracking-wider text-[#6B726C] font-medium">Company</th>
                <th className="px-6 py-3 text-xs uppercase tracking-wider text-[#6B726C] font-medium">Default supplier</th>
                <th className="px-6 py-3"></th>
              </tr>
            </thead>
            <tbody data-testid="medicines-table">
              {loading ? (
                <tr><td colSpan={4} className="px-6 py-10 text-center text-[#6B726C]">Loading…</td></tr>
              ) : medicines.length === 0 ? (
                <tr><td colSpan={4} className="px-6 py-14 text-center text-[#6B726C]">
                  No medicines yet. Import from Tally or add one manually.
                </td></tr>
              ) : (
                medicines.map((m) => (
                  <tr key={m.id} className="border-t border-[#E5E1DB] hover:bg-[#F9F8F6]" data-testid={`medicine-row-${m.id}`}>
                    <td className="px-6 py-3 text-[#2C312E] font-medium">{m.name}</td>
                    <td className="px-6 py-3 text-[#6B726C]">{m.company || "—"}</td>
                    <td className="px-6 py-3 text-[#2C312E]">
                      {m.default_supplier_name || <span className="text-[#B04A3A]">Unassigned</span>}
                      {m.other_suppliers?.length > 0 && (
                        <div className="text-xs text-[#6B726C] mt-0.5" data-testid={`other-suppliers-${m.id}`}>
                          Also from: {m.other_suppliers.join(", ")}
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-3 text-right">
                      <button data-testid={`edit-medicine-${m.id}`} onClick={() => openEdit(m)} className="p-2 rounded-full text-[#6B726C] hover:bg-[#F2EFEB]">
                        <Pencil size={14} />
                      </button>
                      <button data-testid={`delete-medicine-${m.id}`} onClick={() => remove(m.id)} className="p-2 rounded-full text-[#6B726C] hover:bg-[#F7E9E4] hover:text-[#B04A3A]">
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showTally && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-[#2C312E]/40 backdrop-blur-sm px-4 overflow-y-auto py-8">
          <div className="bg-white rounded-3xl border border-[#E5E1DB] max-w-lg w-full p-8" data-testid="tally-dialog">
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="text-xs uppercase tracking-[0.25em] text-[#6B726C]">Tally Prime</div>
                <h3 className="font-serif text-3xl mt-1 text-[#2C312E]">Import purchase bills</h3>
              </div>
              <button type="button" onClick={() => setShowTally(false)} className="p-2 rounded-full hover:bg-[#F2EFEB]"><X size={18} /></button>
            </div>

            {!tallyResult ? (
              <>
                <p className="text-sm text-[#6B726C]">
                  The app reads your purchase bills and learns which item comes from which party (supplier).
                  An item bought from several parties is linked to all of them.
                </p>
                <div className="mt-4 rounded-2xl bg-[#F9F8F6] border border-[#E5E1DB] p-4 text-sm text-[#2C312E]">
                  <div className="font-medium mb-2">Tally Prime से file कैसे निकालें / How to export:</div>
                  <ol className="list-decimal pl-5 space-y-1 text-[#4A4F4B]">
                    <li><b>Gateway of Tally</b> पर <b>Alt+E</b> (Export) दबाएँ → <b>Transactions</b></li>
                    <li>Voucher type: <b>Purchase</b> (या All Vouchers) / pick Purchase</li>
                    <li>Period: From – To चुनें (जैसे पूरा साल) / choose the dates</li>
                    <li><b>File Format</b>: <b>XML (Data Interchange)</b>, folder note कर लें</li>
                    <li><b>Send</b> दबाएँ, फिर वो <b>.xml</b> file नीचे चुनें / pick that file below</li>
                  </ol>
                  <div className="text-xs text-[#6B726C] mt-2">Day Book का XML export भी चलेगा: सिर्फ़ purchase bills पढ़े जाते हैं, sales वग़ैरह छोड़ दिए जाते हैं।</div>
                </div>

                <label className="mt-5 block">
                  <span className="block text-xs uppercase tracking-wider text-[#6B726C] mb-2">Tally XML file</span>
                  <input
                    data-testid="tally-file-input"
                    type="file"
                    accept=".xml"
                    onChange={(e) => setTallyFile(e.target.files?.[0] || null)}
                    className="block w-full text-sm file:mr-3 file:px-4 file:py-2 file:rounded-full file:border-0 file:bg-[#F2EFEB] file:text-[#2C312E]"
                  />
                </label>
                <label className="mt-4 flex items-start gap-2 text-sm text-[#4A4F4B]">
                  <input type="checkbox" className="mt-1" checked={tallyUpdateDefaults} onChange={(e) => setTallyUpdateDefaults(e.target.checked)} />
                  <span>
                    Also change existing default suppliers to the party with the most bills.
                    <span className="block text-xs text-[#6B726C]">Leave unticked to keep the defaults you already set. New items always get the most-used party.</span>
                  </span>
                </label>
                <div className="mt-6 flex justify-end gap-3">
                  <button onClick={() => setShowTally(false)} className="pill-btn px-5 py-2.5 border border-[#E5E1DB]">Cancel</button>
                  <button
                    data-testid="tally-import-submit"
                    disabled={!tallyFile || tallyBusy}
                    onClick={submitTally}
                    className="pill-btn px-6 py-2.5 bg-[#4A5D4E] text-white disabled:opacity-40"
                  >
                    {tallyBusy ? "Reading bills…" : "Import"}
                  </button>
                </div>
              </>
            ) : (
              <div data-testid="tally-result">
                <div className="text-[#2C312E] font-medium">Import complete ✓</div>
                <ul className="mt-3 space-y-1.5 text-sm text-[#4A4F4B]">
                  <li>Purchase bills read: <b>{tallyResult.bills_found}</b>
                    {tallyResult.bills_already_imported > 0 && <span className="text-[#6B726C]"> ({tallyResult.bills_already_imported} were already imported earlier, skipped)</span>}
                  </li>
                  <li>New suppliers (parties) added: <b>{tallyResult.new_suppliers}</b></li>
                  <li>New items added: <b>{tallyResult.new_medicines}</b></li>
                  <li>New item–supplier links: <b>{tallyResult.links}</b></li>
                  <li>Default suppliers set: <b>{tallyResult.defaults_set}</b></li>
                </ul>
                <div className="mt-6 flex justify-end">
                  <button onClick={() => setShowTally(false)} className="pill-btn px-6 py-2.5 bg-[#4A5D4E] text-white">Done</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-[#2C312E]/40 backdrop-blur-sm px-4">
          <form onSubmit={submit} className="bg-white rounded-3xl border border-[#E5E1DB] max-w-md w-full p-8">
            <div className="flex items-center justify-between mb-6">
              <div>
                <div className="text-xs uppercase tracking-[0.25em] text-[#6B726C]">Medicine</div>
                <h3 className="font-serif text-3xl mt-1 text-[#2C312E]">{editing ? "Edit" : "New"}</h3>
              </div>
              <button type="button" onClick={() => setShowForm(false)} className="p-2 rounded-full hover:bg-[#F2EFEB]"><X size={18} /></button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs uppercase tracking-wider text-[#6B726C] mb-2">Name</label>
                <input data-testid="medicine-name-input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full px-4 py-3 rounded-xl bg-white border border-[#E5E1DB] focus:outline-none focus:ring-2 focus:ring-[#4A5D4E]/40" />
              </div>
              <div>
                <label className="block text-xs uppercase tracking-wider text-[#6B726C] mb-2">Company</label>
                <input data-testid="medicine-company-input" value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })}
                  className="w-full px-4 py-3 rounded-xl bg-white border border-[#E5E1DB] focus:outline-none focus:ring-2 focus:ring-[#4A5D4E]/40" />
              </div>
              <div>
                <label className="block text-xs uppercase tracking-wider text-[#6B726C] mb-2">Default supplier</label>
                <select data-testid="medicine-supplier-select" value={form.default_supplier_id} onChange={(e) => setForm({ ...form, default_supplier_id: e.target.value })}
                  className="w-full px-4 py-3 rounded-xl bg-white border border-[#E5E1DB] focus:outline-none focus:ring-2 focus:ring-[#4A5D4E]/40">
                  <option value="">— Unassigned —</option>
                  {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
            </div>
            <div className="mt-8 flex justify-end gap-3">
              <button type="button" onClick={() => setShowForm(false)} className="pill-btn px-5 py-2.5 border border-[#E5E1DB]">Cancel</button>
              <button data-testid="save-medicine-btn" type="submit" className="pill-btn px-6 py-2.5 bg-[#4A5D4E] text-white">Save</button>
            </div>
          </form>
        </div>
      )}

      {showPaste && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-[#2C312E]/40 backdrop-blur-sm px-4">
          <div className="bg-white rounded-3xl border border-[#E5E1DB] max-w-2xl w-full p-8">
            <div className="flex items-center justify-between mb-2">
              <div>
                <div className="text-xs uppercase tracking-[0.25em] text-[#6B726C]">Import</div>
                <h3 className="font-serif text-3xl mt-1 text-[#2C312E]">Paste rows</h3>
              </div>
              <button onClick={() => setShowPaste(false)} className="p-2 rounded-full hover:bg-[#F2EFEB]"><X size={18} /></button>
            </div>
            <p className="text-sm text-[#6B726C] mb-4">Comma-separated: <span className="font-mono">medicine_name, company, supplier</span> (one per line).</p>
            <textarea
              data-testid="paste-textarea"
              value={pasteText}
              onChange={(e) => setPasteText(e.target.value)}
              rows={10}
              placeholder={"Paracetamol 500, Cipla, Cipla Distributors\nAmoxicillin, GSK, MedPlus"}
              className="w-full px-4 py-3 rounded-xl bg-white border border-[#E5E1DB] font-mono text-sm focus:outline-none focus:ring-2 focus:ring-[#4A5D4E]/40"
            />
            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => setShowPaste(false)} className="pill-btn px-5 py-2.5 border border-[#E5E1DB]">Cancel</button>
              <button data-testid="paste-import-btn" onClick={submitPaste} className="pill-btn px-6 py-2.5 bg-[#4A5D4E] text-white">Import</button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
