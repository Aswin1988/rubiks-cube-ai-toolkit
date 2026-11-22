import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cube Lab — Verified Rubik's Cube",
  description: "Interactive 3D demonstration of the verified Rubik's Cube AI Toolkit.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
