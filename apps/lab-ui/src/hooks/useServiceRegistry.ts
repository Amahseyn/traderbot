/**
 * Service Registry Hook — discover available backend services
 *
 * This hook queries /api/infrastructure/services to know what's available
 * and adapts the UI accordingly (feature flags, fallbacks, etc.)
 */

import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";

export interface ServiceInfo {
  type: string;
  module: string;
}

export interface ServicesRegistry {
  services: Record<string, ServiceInfo>;
}

export function useServiceRegistry() {
  const [services, setServices] = useState<ServicesRegistry | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchServices = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/infrastructure/services`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setServices(data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setServices(null);
      } finally {
        setLoading(false);
      }
    };

    fetchServices();
  }, []);

  const hasService = (serviceType: string): boolean => {
    return services?.services[serviceType] !== undefined;
  };

  return { services, loading, error, hasService };
}
