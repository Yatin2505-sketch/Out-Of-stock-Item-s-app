import React, { useEffect, useState, useCallback } from "react";
import AppShell from "../components/AppShell";
import { api, formatApiError } from "../lib/api";
import { toast } from "sonner";
import { Plus, Trash2, User, KeyRound } from "lucide-react";

export default function Settings() {
  const [suppliers, setSuppliers] = useState([]);
  const [supplierName, setSupplierName] = useState("");
  const [users, setUsers] = useState([]);
  const [newUser, setNewUser] = useState({ name: "", username: "", password: "", role: "employee" });

  const load = useCallback(async () => {
    try {
      const [s, u] = await Promise.all([api.get("/suppliers"), api.get("/users")]);
      setSuppliers(s.data); setUsers(u.data);
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const addSupplier = async (e) => {
    e.preventDefault();
    if (!supplierName.trim()) return;
    try {
      await api.post("/suppliers", { name: supplierName });
      setSupplierName(""); load(); toast.success("Supplier added");
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const deleteSupplier = async (id) => {
    if (!window.confirm("Delete this supplier? Medicines will become unassigned.")) return;
    try { await api.delete(`/suppliers/${id}`); load(); } catch { toast.error("Failed"); }
  };

  const addUser = async (e) => {
    e.preventDefault();
    try {
      await api.post("/users", newUser);
      setNewUser({ name: "", username: "", password: "", role: "employee" });
      load(); toast.success("Account created");
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const resetPassword = async (u) => {
    const password = window.prompt(`New password for ${u.name} (${u.username}):`);
    if (password === null) return;
    if (password.length < 4) { toast.error("Password must be at least 4 characters"); return; }
    try {
      await api.put(`/users/${u.id}/password`, { password });
      toast.success(`Password changed for ${u.name}`);
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const deleteUser = async (id) => {
    if (!window.confirm("Delete this user?")) return;
    try { await api.delete(`/users/${id}`); load(); } catch { toast.error("Failed"); }
  };

  return (
    <AppShell>
      <div className="px-4 md:px-10 py-8 max-w-5xl">
        <div className="mb-10">
          <div className="text-xs uppercase tracking-[0.25em] text-[#6B726C]">Configuration</div>
          <h1 className="font-serif text-4xl md:text-5xl mt-1 text-[#2C312E]">Settings</h1>
        </div>

        <div className="grid md:grid-cols-2 gap-6">
          {/* Suppliers */}
          <div className="bg-white rounded-2xl border border-[#E5E1DB] p-6">
            <h2 className="font-serif text-2xl text-[#2C312E]">Suppliers</h2>
            <p className="text-sm text-[#6B726C] mt-1">Columns on the daily board.</p>
            <form onSubmit={addSupplier} className="mt-5 flex gap-2">
              <input
                data-testid="supplier-name-input"
                value={supplierName}
                onChange={(e) => setSupplierName(e.target.value)}
                placeholder="Supplier name"
                className="flex-1 px-4 py-2.5 rounded-full bg-white border border-[#E5E1DB] focus:outline-none focus:ring-2 focus:ring-[#4A5D4E]/40"
              />
              <button data-testid="add-supplier-btn" type="submit" className="pill-btn inline-flex items-center gap-2 px-5 py-2.5 bg-[#4A5D4E] text-white text-sm">
                <Plus size={16} /> Add
              </button>
            </form>
            <ul className="mt-4 space-y-1.5" data-testid="suppliers-list">
              {suppliers.length === 0 && <li className="text-sm text-[#6B726C] py-4 text-center">No suppliers yet.</li>}
              {suppliers.map((s) => (
                <li key={s.id} className="flex items-center justify-between px-4 py-2.5 rounded-xl bg-[#F9F8F6] border border-[#E5E1DB]" data-testid={`supplier-${s.id}`}>
                  <span className="text-[#2C312E]">{s.name}</span>
                  <button data-testid={`delete-supplier-${s.id}`} onClick={() => deleteSupplier(s.id)} className="p-2 rounded-full text-[#6B726C] hover:text-[#B04A3A] hover:bg-[#F7E9E4]">
                    <Trash2 size={14} />
                  </button>
                </li>
              ))}
            </ul>
          </div>

          {/* Users */}
          <div className="bg-white rounded-2xl border border-[#E5E1DB] p-6">
            <h2 className="font-serif text-2xl text-[#2C312E]">Team accounts</h2>
            <p className="text-sm text-[#6B726C] mt-1">Create logins for father, staff and yourself.</p>
            <form onSubmit={addUser} className="mt-5 space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <input data-testid="new-user-name" required value={newUser.name} onChange={(e) => setNewUser({ ...newUser, name: e.target.value })} placeholder="Name" className="px-4 py-2.5 rounded-xl border border-[#E5E1DB] focus:outline-none focus:ring-2 focus:ring-[#4A5D4E]/40" />
                <select data-testid="new-user-role" value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value })} className="px-4 py-2.5 rounded-xl border border-[#E5E1DB] bg-white focus:outline-none focus:ring-2 focus:ring-[#4A5D4E]/40">
                  <option value="employee">Employee</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <input data-testid="new-user-email" type="text" autoCapitalize="none" required value={newUser.username} onChange={(e) => setNewUser({ ...newUser, username: e.target.value })} placeholder="Username (used to log in)" className="w-full px-4 py-2.5 rounded-xl border border-[#E5E1DB] focus:outline-none focus:ring-2 focus:ring-[#4A5D4E]/40" />
              <input data-testid="new-user-password" type="text" required value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} placeholder="Temporary password" className="w-full px-4 py-2.5 rounded-xl border border-[#E5E1DB] focus:outline-none focus:ring-2 focus:ring-[#4A5D4E]/40" />
              <button data-testid="create-user-btn" type="submit" className="pill-btn w-full px-5 py-2.5 bg-[#4A5D4E] text-white text-sm">Create account</button>
            </form>
            <ul className="mt-6 space-y-1.5" data-testid="users-list">
              {users.map((u) => (
                <li key={u.id} className="flex items-center justify-between px-4 py-2.5 rounded-xl bg-[#F9F8F6] border border-[#E5E1DB]" data-testid={`user-${u.id}`}>
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center text-[#4A5D4E]"><User size={14} /></div>
                    <div className="min-w-0">
                      <div className="text-[#2C312E] truncate">{u.name}</div>
                      <div className="text-xs text-[#6B726C] truncate">{u.username} · {u.role}</div>
                    </div>
                  </div>
                  <div className="flex items-center">
                  <button data-testid={`reset-password-${u.id}`} onClick={() => resetPassword(u)} title="Change password" className="p-2 rounded-full text-[#6B726C] hover:text-[#2C312E] hover:bg-white">
                    <KeyRound size={14} />
                  </button>
                  <button data-testid={`delete-user-${u.id}`} onClick={() => deleteUser(u.id)} className="p-2 rounded-full text-[#6B726C] hover:text-[#B04A3A] hover:bg-[#F7E9E4]">
                    <Trash2 size={14} />
                  </button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
