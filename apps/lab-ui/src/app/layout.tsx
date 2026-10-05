import type { Metadata } from "next";
import { ApiOfflineBanner } from "@/components/ApiOfflineBanner";
import { Nav } from "@/components/Nav";
import { Providers } from "@/components/Providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Traderbot Lab",
  description: "Data, lab jobs, and evaluation runs for strategy and ML research",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-surface">
        <Providers>
          <ApiOfflineBanner />
          <Nav />
          <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
