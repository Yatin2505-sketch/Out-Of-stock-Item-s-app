import React, { useEffect, useState, useMemo, useCallback } from "react";
import AppShell from "../components/AppShell";
import { api, formatApiError, API } from "../lib/api";
import { DragDropContext, Droppable, Draggable } from "@hello-pangea/dnd";
import { toast } from "sonner";
import { Download, Copy, CopyPlus, Calendar, Trash2, PackageOpen, Pencil, LayoutGrid, List, HelpCircle, Plus } from "lucide-react";
import MedicineAutocomplete from "../components/MedicineAutocomplete";

const UNASSIGNED = "unassigned";

export default function AdminHome() {
  const [suppliers, setSuppliers] = useState([]);
  const [logs, setLogs] = useState([]);
  const [date, setDate] = useState(() => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; });
  const [loading, setLoading] = useState(true);

  // Admin quick add
  const [name, setName] = useState("");
  const [selected, setSelected] = useState(null);
  const [quantity, setQuantity] = useState("");
  const [showQty, setShowQty] = useState(false);

  // Views from the spec: Supplier list (board) / Short item list / Unclassified item list
  const [view, setView] = useState("board");
  // Edit dialog
  const [editing, setEditing] = useState(null); // { id, medicine_name, quantity }
  // Pending supplier choice per unclassified row: { [logId]: { supplierId, remember } }
  const [classify, setClassify] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [sRes, lRes] = await Promise.all([
        api.get("/suppliers"),
        api.get("/logs", { params: { date } }),
      ]);
      setSuppliers(sRes.data);
      setLogs(lRes.data);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setLoading(false); }
  }, [date]);

  useEffect(() => { load(); }, [load]);

  const columns = useMemo(() => {
    const map = new Map();
    map.set(UNASSIGNED, { id: UNASSIGNED, name: "Unassigned", items: [] });
    suppliers.forEach((s) => map.set(s.id, { id: s.id, name: s.name, items: [] }));
    logs.forEach((l) => {
      const key = l.supplier_id || UNASSIGNED;
      if (!map.has(key)) map.set(key, { id: key, name: "Unknown", items: [] });
      map.get(key).items.push(l);
    });
    return Array.from(map.values());
  }, [logs, suppliers]);

  const onDragEnd = async (result) => {
    if (!result.destination) return;
    const { draggableId, destination, source } = result;
    if (destination.droppableId === source.droppableId) return;
    const newSupplierId = destination.droppableId === UNASSIGNED ? null : destination.droppableId;
    // optimistic
    setLogs((prev) =>
      prev.map((l) => (l.id === draggableId ? { ...l, supplier_id: newSupplierId, status: newSupplierId ? "assigned" : "unassigned" } : l))
    );
    try {
      const { data } = await api.put(`/logs/${draggableId}/assign`, { supplier_id: newSupplierId });
      setLogs((prev) => prev.map((l) => (l.id === data.id ? data : l)));
      if (source.droppableId === UNASSIGNED && newSupplierId) {
        const sup = suppliers.find((s) => s.id === newSupplierId);
        toast.success(`Moved to ${sup?.name || "supplier"} for today`, {
          action: {
            label: "Always use this supplier",
            onClick: () => assign(draggableId, newSupplierId, true),
          },
        });
      }
    } catch (err) {
      toast.error("Failed to move");
      load();
    }
  };

  const assign = async (logId, supplierId, remember) => {
    try {
      const { data } = await api.put(`/logs/${logId}/assign`, { supplier_id: supplierId, remember });
      setLogs((prev) => prev.map((l) => (l.id === logId ? data : l)));
      toast.success(remember ? "Saved as default supplier" : "Supplier set for today");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const saveEdit = async () => {
    try {
      const { data } = await api.put(`/logs/${editing.id}`, {
        medicine_name: editing.medicine_name,
        quantity: editing.quantity,
      });
      setLogs((prev) => prev.map((l) => (l.id === data.id ? data : l)));
      setEditing(null);
      toast.success("Updated");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const bulkDelete = async (supplierId = null, label = "all items for this day") => {
    if (!window.confirm(`Delete ${label}? This cannot be undone.`)) return;
    try {
      const params = { date };
      if (supplierId) params.supplier_id = supplierId;
      const { data } = await api.delete(`/logs`, { params });
      toast.success(`Deleted ${data.deleted} item${data.deleted === 1 ? "" : "s"}`);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const supplierName = (id) => (id ? suppliers.find((s) => s.id === id)?.name || "Unknown" : "Unassigned");
  const unassignedLogs = logs.filter((l) => !l.supplier_id);

  const removeLog = async (id) => {
    try { await api.delete(`/logs/${id}`); setLogs((p) => p.filter((l) => l.id !== id)); }
    catch { toast.error("Failed"); }
  };

  // Duplicate a card: same column (then drag it anywhere), or straight into another supplier
  const copyLog = async (item, supplierId) => {
    try {
      const body = supplierId === undefined ? {} : { supplier_id: supplierId };
      const { data } = await api.post(`/logs/${item.id}/copy`, body);
      setLogs((prev) => {
        const i = prev.findIndex((l) => l.id === item.id);
        const next = [...prev];
        next.splice(i + 1, 0, data);
        return next;
      });
      toast.success(
        supplierId === undefined
          ? "Copied — drag the copy to any supplier"
          : `Copied to ${supplierName(supplierId)}`
      );
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const downloadPDF = async () => {
    try {
      const res = await api.get(`/logs/export/pdf`, { params: { date }, responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `order-list-${date}.pdf`; a.click();
      window.URL.revokeObjectURL(url);
    } catch { toast.error("PDF export failed"); }
  };

  const copyText = async (supplierId = null) => {
    try {
      const params = { date };
      if (supplierId) params.supplier_id = supplierId;
      const { data } = await api.get(`/logs/export/text`, { params });
      await navigator.clipboard.writeText(data.text);
      toast.success("Copied — paste into WhatsApp");
    } catch { toast.error("Copy failed"); }
  };

  const handleSelect = (m) => { setSelected(m); setName(m.name); setQuantity(""); setShowQty(true); };
  const submitAdd = async () => {
    try {
      await api.post("/logs", { medicine_id: selected?.id || null, medicine_name: selected?.name || name, quantity: quantity.trim() });
      toast.success("Added");
      setName(""); setSelected(null); setQuantity(""); setShowQty(false);
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  return (
    <AppShell>
      <div className="px-4 md:px-10 py-8">
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-6 mb-8">
          <div>
            <div className="text-xs uppercase tracking-[0.25em] text-[#6B726C]">Order board</div>
            <h1 className="font-serif text-4xl md:text-5xl mt-1 text-[#2C312E]">Today's shortlist</h1>
            <p className="mt-2 text-[#6B726C] text-sm">Drag any medicine between supplier columns. Defaults stay untouched.</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative">
              <Calendar size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#6B726C] pointer-events-none" />
              <input
                data-testid="date-picker"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="pl-9 pr-4 py-2.5 rounded-full bg-white border border-[#E5E1DB] text-sm focus:outline-none focus:ring-2 focus:ring-[#4A5D4E]/40"
              />
            </div>
            <button
              data-testid="copy-all-btn"
              onClick={() => copyText()}
              className="pill-btn inline-flex items-center gap-2 px-5 py-2.5 border border-[#E5E1DB] bg-white text-sm hover:bg-[#F2EFEB]"
            >
              <Copy size={16} /> Copy for WhatsApp
            </button>
            <button
              data-testid="download-pdf-btn"
              onClick={downloadPDF}
              className="pill-btn inline-flex items-center gap-2 px-5 py-2.5 bg-[#4A5D4E] text-white text-sm hover:bg-[#3D4D40]"
            >
              <Download size={16} /> Download PDF
            </button>
            <button
              data-testid="delete-all-btn"
              onClick={() => bulkDelete()}
              disabled={logs.length === 0}
              className="pill-btn inline-flex items-center gap-2 px-5 py-2.5 border border-[#E5E1DB] bg-white text-sm text-[#B04A3A] hover:bg-[#F7E9E4] disabled:opacity-40"
            >
              <Trash2 size={16} /> Delete all
            </button>
          </div>
        </div>

        {/* Quick add for admin */}
        <div className="mb-8 max-w-2xl">
          <div className="text-xs uppercase tracking-[0.25em] text-[#6B726C] mb-2">Quick note</div>
          <MedicineAutocomplete value={name} onChange={setName} onSelect={handleSelect} testid="admin-medicine-input" />
        </div>

        {/* View tabs */}
        <div className="flex flex-wrap gap-2 mb-6" role="tablist">
          {[
            { id: "board", label: "Supplier list", icon: LayoutGrid, count: null },
            { id: "list", label: "Short item list", icon: List, count: logs.length },
            { id: "unclassified", label: "Unclassified items", icon: HelpCircle, count: unassignedLogs.length },
          ].map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={view === t.id}
              data-testid={`view-tab-${t.id}`}
              onClick={() => setView(t.id)}
              className={`pill-btn inline-flex items-center gap-2 px-4 py-2 text-sm border ${
                view === t.id ? "bg-[#2C312E] text-white border-[#2C312E]" : "bg-white border-[#E5E1DB] text-[#2C312E] hover:bg-[#F2EFEB]"
              }`}
            >
              <t.icon size={15} /> {t.label}
              {t.count !== null && <span className="text-xs opacity-70">({t.count})</span>}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="text-[#6B726C] font-serif text-2xl py-20 text-center">Loading…</div>
        ) : view === "list" ? (
          <div className="bg-white rounded-2xl border border-[#E5E1DB] overflow-x-auto" data-testid="short-item-list">
            <table className="w-full text-sm">
              <thead className="bg-[#F2EFEB] text-left text-[11px] uppercase tracking-wider text-[#6B726C]">
                <tr>
                  <th className="px-4 py-3">Item name</th>
                  <th className="px-4 py-3">Quantity left</th>
                  <th className="px-4 py-3">Supplier</th>
                  <th className="px-4 py-3">Added by</th>
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {logs.length === 0 && (
                  <tr><td colSpan={6} className="px-4 py-10 text-center text-[#6B726C]">No items noted on this day.</td></tr>
                )}
                {logs.map((l) => (
                  <tr key={l.id} className="border-t border-[#E5E1DB]" data-testid={`list-row-${l.id}`}>
                    <td className="px-4 py-3">
                      <div className="font-medium text-[#2C312E]">{l.medicine_name}</div>
                      {l.company && <div className="text-xs text-[#6B726C]">{l.company}</div>}
                    </td>
                    <td className="px-4 py-3">{l.quantity || "—"}</td>
                    <td className="px-4 py-3">{supplierName(l.supplier_id)}</td>
                    <td className="px-4 py-3">{l.added_by_name}</td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {l.date}
                      {l.created_at && (
                        <span className="text-xs text-[#6B726C] ml-1">
                          {new Date(l.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      <button onClick={() => setEditing({ id: l.id, medicine_name: l.medicine_name, quantity: l.quantity || "" })} className="p-1.5 rounded-full text-[#6B726C] hover:text-[#2C312E] hover:bg-[#F2EFEB]" title="Edit"><Pencil size={14} /></button>
                      <button onClick={() => removeLog(l.id)} className="p-1.5 rounded-full text-[#6B726C] hover:text-[#B04A3A] hover:bg-[#F7E9E4]" title="Delete"><Trash2 size={14} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : view === "unclassified" ? (
          <div className="bg-white rounded-2xl border border-[#E5E1DB] overflow-x-auto" data-testid="unclassified-list">
            <table className="w-full text-sm">
              <thead className="bg-[#F2EFEB] text-left text-[11px] uppercase tracking-wider text-[#6B726C]">
                <tr>
                  <th className="px-4 py-3">Item name</th>
                  <th className="px-4 py-3">Quantity left</th>
                  <th className="px-4 py-3">Added by</th>
                  <th className="px-4 py-3">Choose supplier</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {unassignedLogs.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-10 text-center text-[#6B726C]">Nothing unclassified — every item has a supplier.</td></tr>
                )}
                {unassignedLogs.map((l) => {
                  const c = classify[l.id] || { supplierId: "", remember: true };
                  const setC = (patch) => setClassify((p) => ({ ...p, [l.id]: { ...c, ...patch } }));
                  return (
                    <tr key={l.id} className="border-t border-[#E5E1DB]" data-testid={`unclassified-row-${l.id}`}>
                      <td className="px-4 py-3">
                        <div className="font-medium text-[#2C312E]">{l.medicine_name}</div>
                        {!l.medicine_id && <div className="text-[11px] text-[#B04A3A]">Not in medicine database</div>}
                      </td>
                      <td className="px-4 py-3">{l.quantity || "—"}</td>
                      <td className="px-4 py-3">{l.added_by_name}</td>
                      <td className="px-4 py-3">
                        <select
                          data-testid={`classify-select-${l.id}`}
                          value={c.supplierId}
                          onChange={(e) => setC({ supplierId: e.target.value })}
                          className="px-3 py-2 rounded-lg border border-[#E5E1DB] bg-white"
                        >
                          <option value="">Select…</option>
                          {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                        </select>
                        <label className="ml-3 inline-flex items-center gap-1.5 text-xs text-[#6B726C]">
                          <input type="checkbox" checked={c.remember} onChange={(e) => setC({ remember: e.target.checked })} />
                          Remember for next time
                        </label>
                      </td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <button
                          data-testid={`classify-save-${l.id}`}
                          disabled={!c.supplierId}
                          onClick={() => assign(l.id, c.supplierId, c.remember)}
                          className="pill-btn px-4 py-1.5 bg-[#4A5D4E] text-white text-xs disabled:opacity-40"
                        >
                          Assign
                        </button>
                        <button onClick={() => removeLog(l.id)} className="ml-1 p-1.5 rounded-full text-[#6B726C] hover:text-[#B04A3A] hover:bg-[#F7E9E4]" title="Delete"><Trash2 size={14} /></button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <DragDropContext onDragEnd={onDragEnd}>
            <div className="flex gap-5 overflow-x-auto pb-6" data-testid="kanban-board">
              {columns.map((col) => (
                <Droppable droppableId={col.id} key={col.id}>
                  {(provided, snapshot) => (
                    <div
                      ref={provided.innerRef}
                      {...provided.droppableProps}
                      className={`kanban-column ${snapshot.isDraggingOver ? "is-drop-target" : ""} flex-shrink-0`}
                      data-testid={`column-${col.id}`}
                    >
                      <div className="px-4 pt-4 pb-3 sticky top-0 bg-[#F2EFEB] rounded-t-2xl z-10 border-b border-[#E5E1DB]/70">
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="text-[10px] uppercase tracking-[0.25em] text-[#6B726C]">Supplier</div>
                            <h3 className="font-serif text-xl text-[#2C312E] mt-0.5">{col.name}</h3>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="inline-flex items-center justify-center min-w-[24px] h-6 px-2 rounded-full bg-white text-[11px] font-medium text-[#4A5D4E] border border-[#E5E1DB]">
                              {col.items.length}
                            </span>
                            <button
                              data-testid={`copy-column-${col.id}`}
                              onClick={() => copyText(col.id)}
                              className="p-1.5 rounded-full text-[#6B726C] hover:text-[#2C312E] hover:bg-white"
                              title="Copy this column"
                            >
                              <Copy size={14} />
                            </button>
                            <button
                              data-testid={`clear-column-${col.id}`}
                              onClick={() => bulkDelete(col.id, `all ${col.items.length} item(s) under ${col.name}`)}
                              disabled={col.items.length === 0}
                              className="p-1.5 rounded-full text-[#6B726C] hover:text-[#B04A3A] hover:bg-white disabled:opacity-30"
                              title="Delete all items in this column"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </div>
                      </div>
                      <div className="p-3 space-y-2 overflow-y-auto flex-1 min-h-[100px]">
                        {col.items.length === 0 && (
                          <div className="text-xs text-[#6B726C] text-center py-8 opacity-70">
                            <PackageOpen size={20} className="mx-auto mb-2" />
                            No items
                          </div>
                        )}
                        {col.items.map((item, index) => (
                          <Draggable draggableId={item.id} index={index} key={item.id}>
                            {(prov, snap) => (
                              <div
                                ref={prov.innerRef}
                                {...prov.draggableProps}
                                {...prov.dragHandleProps}
                                data-testid={`log-card-${item.id}`}
                                className={`kanban-card ${snap.isDragging ? "is-dragging" : ""}`}
                              >
                                <div className="flex items-start justify-between gap-2">
                                  <div className="min-w-0 flex-1">
                                    <div className="font-medium text-[#2C312E] text-[15px] leading-snug">{item.medicine_name}</div>
                                    {item.company && <div className="text-xs text-[#6B726C] mt-0.5">{item.company}</div>}
                                    <div className="flex items-center gap-2 mt-2">
                                      <span className="text-[11px] uppercase tracking-wider text-[#6B726C]">Left</span>
                                      <span className="text-sm text-[#2C312E]">{item.quantity || "—"}</span>
                                    </div>
                                    <div className="text-[11px] text-[#6B726C] mt-2">by {item.added_by_name}</div>
                                    {item.alt_suppliers?.length > 0 && (
                                      <div className="mt-2 pt-2 border-t border-[#E5E1DB]/70" data-testid={`alt-suppliers-${item.id}`}>
                                        <div className="text-[10px] uppercase tracking-wider text-[#6B726C] mb-1">Also from</div>
                                        <div className="flex flex-wrap gap-1">
                                          {item.alt_suppliers.map((s) => (
                                            <button
                                              key={s.id}
                                              data-testid={`copy-to-${item.id}-${s.id}`}
                                              onClick={() => copyLog(item, s.id)}
                                              title={`Add a copy under ${s.name}`}
                                              className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full border border-[#E5E1DB] bg-[#F9F8F6] text-[11px] text-[#4A5D4E] hover:bg-[#4A5D4E] hover:text-white"
                                            >
                                              <Plus size={10} /> {s.name}
                                            </button>
                                          ))}
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                  <div className="flex flex-col">
                                  <button
                                    data-testid={`copy-log-${item.id}`}
                                    onClick={() => copyLog(item)}
                                    className="p-1.5 rounded-full text-[#6B726C] hover:text-[#2C312E] hover:bg-[#F2EFEB]"
                                    title="Copy — then drag the copy to another supplier"
                                  >
                                    <CopyPlus size={14} />
                                  </button>
                                  <button
                                    data-testid={`edit-log-${item.id}`}
                                    onClick={() => setEditing({ id: item.id, medicine_name: item.medicine_name, quantity: item.quantity || "" })}
                                    className="p-1.5 rounded-full text-[#6B726C] hover:text-[#2C312E] hover:bg-[#F2EFEB]"
                                    title="Edit"
                                  >
                                    <Pencil size={14} />
                                  </button>
                                  <button
                                    data-testid={`delete-log-${item.id}`}
                                    onClick={() => removeLog(item.id)}
                                    className="p-1.5 rounded-full text-[#6B726C] hover:text-[#B04A3A] hover:bg-[#F7E9E4]"
                                  >
                                    <Trash2 size={14} />
                                  </button>
                                  </div>
                                </div>
                              </div>
                            )}
                          </Draggable>
                        ))}
                        {provided.placeholder}
                      </div>
                    </div>
                  )}
                </Droppable>
              ))}
            </div>
          </DragDropContext>
        )}
      </div>

      {showQty && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-[#2C312E]/40 backdrop-blur-sm px-4">
          <div className="bg-white rounded-3xl border border-[#E5E1DB] max-w-md w-full p-8">
            <div className="text-xs uppercase tracking-[0.25em] text-[#6B726C]">Quantity left</div>
            <h3 className="font-serif text-3xl mt-1 text-[#2C312E]">{selected?.name || name}</h3>
            {selected?.company && <div className="text-sm text-[#6B726C] mt-1">{selected.company}</div>}
            <input
              data-testid="admin-quantity-input"
              autoFocus
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              placeholder="e.g. 3 strips"
              className="mt-6 w-full px-4 py-3 rounded-xl bg-white border border-[#E5E1DB] focus:outline-none focus:ring-2 focus:ring-[#4A5D4E]/40"
            />
            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => setShowQty(false)} className="pill-btn px-5 py-2.5 border border-[#E5E1DB]">Cancel</button>
              <button data-testid="admin-submit-quantity" onClick={submitAdd} className="pill-btn px-6 py-2.5 bg-[#4A5D4E] text-white">Save</button>
            </div>
          </div>
        </div>
      )}
      {editing && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-[#2C312E]/40 backdrop-blur-sm px-4">
          <div className="bg-white rounded-3xl border border-[#E5E1DB] max-w-md w-full p-8" data-testid="edit-log-dialog">
            <div className="text-xs uppercase tracking-[0.25em] text-[#6B726C]">Edit entry</div>
            <label className="block mt-6 text-xs text-[#6B726C]">Medicine name</label>
            <input
              data-testid="edit-log-name"
              value={editing.medicine_name}
              onChange={(e) => setEditing({ ...editing, medicine_name: e.target.value })}
              className="mt-1 w-full px-4 py-3 rounded-xl bg-white border border-[#E5E1DB] focus:outline-none focus:ring-2 focus:ring-[#4A5D4E]/40"
            />
            <label className="block mt-4 text-xs text-[#6B726C]">Quantity left</label>
            <input
              data-testid="edit-log-quantity"
              value={editing.quantity}
              onChange={(e) => setEditing({ ...editing, quantity: e.target.value })}
              className="mt-1 w-full px-4 py-3 rounded-xl bg-white border border-[#E5E1DB] focus:outline-none focus:ring-2 focus:ring-[#4A5D4E]/40"
            />
            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => setEditing(null)} className="pill-btn px-5 py-2.5 border border-[#E5E1DB]">Cancel</button>
              <button data-testid="edit-log-save" onClick={saveEdit} className="pill-btn px-6 py-2.5 bg-[#4A5D4E] text-white">Save</button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
