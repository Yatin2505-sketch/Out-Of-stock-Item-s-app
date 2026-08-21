import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { LogOut, LayoutDashboard, PillBottle, Settings, Menu } from "lucide-react";
import { useState } from "react";

const adminNav = [
  { to: "/admin", label: "Today's Board", icon: LayoutDashboard, testid: "nav-admin-home" },
  { to: "/admin/medicines", label: "Medicine Database", icon: PillBottle, testid: "nav-medicines" },
  { to: "/admin/settings", label: "Settings", icon: Settings, testid: "nav-settings" },
];

export default function AppShell({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const isAdmin = user?.role === "admin";

  return (
    <div className="min-h-screen bg-[#F9F8F6] text-[#2C312E] flex flex-col md:flex-row">
      {/* Sidebar (admin) */}
      {isAdmin && (
        <aside className={`${open ? "block" : "hidden"} md:block md:w-64 md:min-h-screen border-r border-[#E5E1DB] bg-[#F2EFEB]/60 backdrop-blur-sm px-6 py-8`}>
          <div className="mb-10">
            <div className="text-xs uppercase tracking-[0.25em] text-[#6B726C]">Pharmacy</div>
            <h1 className="font-serif text-3xl mt-1 text-[#4A5D4E]">Stockbook</h1>
          </div>
          <nav className="space-y-1">
            {adminNav.map((n) => {
              const Icon = n.icon;
              return (
                <NavLink
                  key={n.to}
                  to={n.to}
                  end
                  data-testid={n.testid}
                  onClick={() => setOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-4 py-3 rounded-full transition-colors duration-200 ${
                      isActive
                        ? "bg-[#4A5D4E] text-white"
                        : "text-[#2C312E] hover:bg-[#E5E1DB]"
                    }`
                  }
                >
                  <Icon size={18} />
                  <span className="text-sm">{n.label}</span>
                </NavLink>
              );
            })}
          </nav>
        </aside>
      )}

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="border-b border-[#E5E1DB] bg-[#F9F8F6]/80 backdrop-blur-md sticky top-0 z-30">
          <div className="flex items-center justify-between px-4 md:px-10 py-4">
            <div className="flex items-center gap-3">
              {isAdmin && (
                <button
                  data-testid="menu-toggle"
                  onClick={() => setOpen((v) => !v)}
                  className="md:hidden p-2 rounded-full hover:bg-[#E5E1DB]"
                >
                  <Menu size={20} />
                </button>
              )}
              <div>
                <div className="text-xs uppercase tracking-[0.2em] text-[#6B726C]">
                  {isAdmin ? "Admin" : "Team"}
                </div>
                <div className="font-serif text-2xl text-[#2C312E]">Welcome, {user?.name}</div>
              </div>
            </div>
            <button
              data-testid="logout-btn"
              onClick={handleLogout}
              className="pill-btn inline-flex items-center gap-2 px-5 py-2 border border-[#E5E1DB] bg-white text-[#2C312E] hover:bg-[#F2EFEB]"
            >
              <LogOut size={16} />
              <span className="text-sm">Logout</span>
            </button>
          </div>
        </header>
        <main className="flex-1 min-w-0">{children}</main>
      </div>
    </div>
  );
}
