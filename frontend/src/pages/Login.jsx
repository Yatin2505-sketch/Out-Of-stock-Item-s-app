import React, { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate, Navigate } from "react-router-dom";
import { formatApiError } from "../lib/api";
import { toast } from "sonner";
import { Eye, EyeOff } from "lucide-react";

const HERO_IMG = "https://images.unsplash.com/photo-1777620843115-a317c59007d6?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1MDV8MHwxfHNlYXJjaHwyfHxhcG90aGVjYXJ5JTIwYm90dGxlcyUyMHZpbnRhZ2V8ZW58MHx8fHwxNzg3Mjk1MDY2fDA&ixlib=rb-4.1.0&q=85";

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  if (user && user.role) {
    return <Navigate to={user.role === "admin" ? "/admin" : "/employee"} replace />;
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const data = await login(email, password);
      toast.success(`Welcome back, ${data.name}`);
      navigate(data.role === "admin" ? "/admin" : "/employee");
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail) || err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-[#F9F8F6]">
      {/* Left visual */}
      <div className="relative hidden lg:block">
        <img src={HERO_IMG} alt="Apothecary" className="absolute inset-0 w-full h-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-br from-[#2C312E]/70 via-[#4A5D4E]/50 to-transparent" />
        <div className="relative z-10 h-full flex flex-col justify-between p-14 text-white">
          <div>
            <div className="text-xs uppercase tracking-[0.35em] opacity-80">Pharmacy · Est. Today</div>
            <h1 className="font-serif text-6xl mt-2 leading-none">Stockbook</h1>
          </div>
          <div className="max-w-md">
            <p className="font-serif text-3xl leading-tight">
              A quiet ledger for what's running low, and where each medicine goes next.
            </p>
            <p className="mt-5 text-sm opacity-80">Suppliers, employees and daily notes — organised without the noise.</p>
          </div>
        </div>
      </div>

      {/* Right form */}
      <div className="flex items-center justify-center px-6 py-14">
        <div className="w-full max-w-md">
          <div className="mb-10">
            <div className="text-xs uppercase tracking-[0.25em] text-[#6B726C]">Sign in</div>
            <h2 className="font-serif text-4xl mt-2 text-[#2C312E]">Open the ledger</h2>
            <p className="mt-3 text-[#6B726C] text-sm">Enter your credentials to continue.</p>
          </div>
          <form onSubmit={handleSubmit} className="space-y-5" data-testid="login-form">
            <div>
              <label className="block text-xs uppercase tracking-wider text-[#6B726C] mb-2">Email</label>
              <input
                data-testid="login-email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full px-4 py-3 rounded-xl bg-white border border-[#E5E1DB] focus:outline-none focus:ring-2 focus:ring-[#4A5D4E]/40 focus:border-[#4A5D4E]"
                placeholder="you@pharmacy.com"
              />
            </div>
            <div>
              <label className="block text-xs uppercase tracking-wider text-[#6B726C] mb-2">Password</label>
              <div className="relative">
                <input
                  data-testid="login-password"
                  type={showPw ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="w-full px-4 py-3 pr-12 rounded-xl bg-white border border-[#E5E1DB] focus:outline-none focus:ring-2 focus:ring-[#4A5D4E]/40 focus:border-[#4A5D4E]"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  data-testid="toggle-password"
                  onClick={() => setShowPw((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#6B726C] hover:text-[#2C312E]"
                >
                  {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>
            {error && (
              <div data-testid="login-error" className="text-sm text-[#B04A3A] bg-[#F7E9E4] border border-[#E9CCC2] rounded-lg px-4 py-3">
                {error}
              </div>
            )}
            <button
              data-testid="login-submit"
              type="submit"
              disabled={submitting}
              className="pill-btn w-full px-6 py-3 bg-[#4A5D4E] text-white hover:bg-[#3D4D40] disabled:opacity-50 transition-colors"
            >
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>
          <p className="mt-10 text-xs text-[#6B726C]">
            Only the admin can create employee accounts. Ask them to invite you.
          </p>
        </div>
      </div>
    </div>
  );
}
