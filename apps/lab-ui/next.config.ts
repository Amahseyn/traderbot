import type { NextConfig } from "next";
import os from "os";

const labApiProxyTarget =
  process.env.LAB_API_PROXY_TARGET?.replace(/\/$/, "") || "http://127.0.0.1:8765";

/**
 * Next.js dev blocks cross-origin `/_next/*` unless the Origin hostname is allowlisted.
 * There is no literal "allow all" flag — use wildcard labels (`*` = one DNS label).
 */
function permissiveAllowedDevOrigins(): string[] {
  const origins = new Set<string>(["127.0.0.1", "localhost", os.hostname()]);

  const fromEnv = process.env.LAB_ALLOWED_DEV_ORIGINS?.split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
  for (const entry of fromEnv ?? []) {
    origins.add(entry);
  }

  for (const iface of Object.values(os.networkInterfaces())) {
    if (!iface) {
      continue;
    }
    for (const address of iface) {
      if (address.family === "IPv4" || address.family === "IPv6") {
        origins.add(address.address);
      }
    }
  }

  for (let labelCount = 2; labelCount <= 16; labelCount += 1) {
    origins.add(Array.from({ length: labelCount }, () => "*").join("."));
  }

  return [...origins];
}

const nextConfig: NextConfig = {
  reactStrictMode: true,
  allowedDevOrigins: permissiveAllowedDevOrigins(),
  async rewrites() {
    return [
      {
        source: "/lab-api/:path*",
        destination: `${labApiProxyTarget}/:path*`,
      },
    ];
  },
};

export default nextConfig;
