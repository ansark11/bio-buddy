"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearToken } from "@/lib/api";

const navLinks = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/upload", label: "Upload" },
];

export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();

  function handleLogout() {
    clearToken();
    router.push("/");
  }

  return (
    <nav className="bg-card border-b border-white/[0.08] px-6 py-3 flex items-center justify-between shrink-0">
      <div className="flex items-center gap-6">
        <span className="font-heading font-semibold text-hblue text-lg tracking-tight">Health RAG</span>
        <div className="flex gap-1">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`text-sm font-medium px-3 py-1.5 rounded-lg transition-colors ${
                pathname === link.href
                  ? "bg-hblue/15 text-hblue"
                  : "text-muted hover:text-ink hover:bg-white/5"
              }`}
            >
              {link.label}
            </Link>
          ))}
        </div>
      </div>
      <button
        onClick={handleLogout}
        className="text-sm text-muted hover:text-bad transition-colors"
      >
        Logout
      </button>
    </nav>
  );
}
