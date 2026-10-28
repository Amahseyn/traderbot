import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { ApiOfflineBanner } from "@/components/ApiOfflineBanner";
import { LabAuthBanner } from "@/components/LabApiAuth";
import { Nav } from "@/components/Nav";
import { PageBackdrop } from "@/components/PageBackdrop";
import { Providers } from "@/components/Providers";
import { SiteFooter } from "@/components/SiteFooter";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: {
    default: "Traderbot Lab",
    template: "%s · Traderbot Lab",
  },
  description: "Data export, strategy research, backtests, and live trading for Traderbot",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="flex min-h-dvh flex-col bg-surface font-sans">
        <PageBackdrop />
        <a href="#main-content" className="skip-link">
          Skip to content
        </a>
        <Providers>
          <ApiOfflineBanner />
          <LabAuthBanner />
          <Nav />
          <main
            id="main-content"
            className="mx-auto w-full max-w-7xl flex-1 px-4 py-7 sm:px-6 sm:py-10"
          >
            {children}
          </main>
          <SiteFooter />
        </Providers>
      </body>
    </html>
  );
}
