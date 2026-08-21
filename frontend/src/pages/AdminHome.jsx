import React, { useEffect, useState, useMemo, useCallback } from "react";
import AppShell from "../components/AppShell";
import { api, formatApiError, API } from "../lib/api";
import { DragDropContext, Droppable, Draggable } from "@hello-pangea/dnd";
import { toast } from "sonner";
import { Download, Copy, Calendar, Trash2, PackageOpen } from "lucide-react";
import MedicineAutocomplete from "../components/MedicineAutocomplete";

const UNASSIGNED = "unassigned";

export default function AdminHome() {
  const [suppliers, setSuppliers] = useState([]);
  const [logs, setLogs] = useState([]);
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [loading, setLoading] = useState(true);

  // Admin quick add
  const [name, setName] = useState("");
  const [selected, setSelected] = useState(null);
  const [quantity, setQuantity] = useState("");
  const [showQty, setShowQty] = useState(false);

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
      await api.put(`/logs/${draggableId}/assign`, { supplier_id: newSupplierId });
    } catch (err) {
      toast.error("Failed to move");
      load();
    }
  };

  const removeLog = async (id) => {
    try { await api.delete(`/logs/${id}`); setLogs((p) => p.filter((l) => l.id !== id)); }
    catch { toast.error("Failed"); }
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
          </div>
        </div>

        {/* Quick add for admin */}
        <div className="mb-8 max-w-2xl">
          <div className="text-xs uppercase tracking-[0.25em] text-[#6B726C] mb-2">Quick note</div>
          <MedicineAutocomplete value={name} onChange={setName} onSelect={handleSelect} testid="admin-medicine-input" />
        </div>

        {/* Kanban */}
        {loading ? (
          <div className="text-[#6B726C] font-serif text-2xl py-20 text-center">Loading…</div>
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
                                  </div>
                                  <button
                                    data-testid={`delete-log-${item.id}`}
                                    onClick={() => removeLog(item.id)}
                                    className="p-1.5 rounded-full text-[#6B726C] hover:text-[#B04A3A] hover:bg-[#F7E9E4]"
                                  >
                                    <Trash2 size={14} />
                                  </button>
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
    </AppShell>
  );
}
