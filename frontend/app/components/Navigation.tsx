"use client";

import Link from "next/link";

export default function Navigation() {
  return (
    <nav className="border-b bg-white">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">

        <Link
          href="/"
          className="text-xl font-bold text-black"
        >
          Terrace Talk
        </Link>

        <Link
          href="/my-stadiums"
          className="border rounded-lg px-4 py-2 font-medium text-black hover:bg-gray-100"
        >
          My Stadiums
        </Link>

      </div>
    </nav>
  );
}