"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { PageHeader } from "@/components/ui/PageHeader";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { api } from "@/lib/api";

const labUiTokenConfigured = Boolean(process.env.NEXT_PUBLIC_LAB_API_TOKEN?.trim());

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const statusQuery = useQuery({ queryKey: ["auth-status"], queryFn: api.authStatus });

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [keyName, setKeyName] = useState("traderbot-lab");
  const [createTotp, setCreateTotp] = useState("");
  const [hlWallet, setHlWallet] = useState("");
  const [hlPrivateKey, setHlPrivateKey] = useState("");

  const hyperliquidQuery = useQuery({
    queryKey: ["auth-hyperliquid"],
    queryFn: api.authHyperliquidAccount,
    enabled: statusQuery.data?.hyperliquid_wallet_configured === true,
    retry: false,
  });

  const saveHyperliquidMutation = useMutation({
    mutationFn: () =>
      api.authSaveHyperliquid({
        wallet_address: hlWallet,
        private_key: hlPrivateKey || undefined,
        write_env: true,
      }),
    onSuccess: () => {
      setHlPrivateKey("");
      void queryClient.invalidateQueries({ queryKey: ["auth-status"] });
      void queryClient.invalidateQueries({ queryKey: ["auth-hyperliquid"] });
    },
  });

  const profileQuery = useQuery({
    queryKey: ["auth-profile"],
    queryFn: api.authProfile,
    enabled: statusQuery.data?.api_keys_configured === true,
    retry: false,
  });

  const keysQuery = useQuery({
    queryKey: ["auth-api-keys"],
    queryFn: api.authApiKeys,
    enabled: statusQuery.data?.auth_token_configured === true,
    retry: false,
  });

  const loginMutation = useMutation({
    mutationFn: () =>
      api.authLogin({
        username,
        password,
        totp: totp || undefined,
        write_env: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auth-status"] });
      queryClient.invalidateQueries({ queryKey: ["auth-profile"] });
      queryClient.invalidateQueries({ queryKey: ["auth-api-keys"] });
    },
  });

  const createKeyMutation = useMutation({
    mutationFn: () =>
      api.authCreateApiKey({
        name: keyName,
        totp: createTotp,
        write_env: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auth-status"] });
      queryClient.invalidateQueries({ queryKey: ["auth-api-keys"] });
      queryClient.invalidateQueries({ queryKey: ["auth-profile"] });
    },
  });

  return (
    <div className="mx-auto max-w-4xl space-y-6 sm:space-y-8">
      <PageHeader
        eyebrow="Configuration"
        title="Settings"
        description="Lab API access, Hyperliquid (default for Live), and Nobitex credentials. Secrets stay on the machine running the Lab API (.env)."
      />

      <Card
        title="Lab API access"
        description="When API auth is enabled, jobs, risk changes, credential writes, and artifact downloads require a bearer token. See docs/live-trading.md in the repo."
      >
        {statusQuery.isLoading && (
          <div className="space-y-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-4 w-3/5" />
          </div>
        )}
        {statusQuery.isError && <ErrorState title="Could not read credential status" error={statusQuery.error} />}
        {statusQuery.data && (
          <ul className="text-sm space-y-1 text-slate-200">
            <li>
              API auth required:{" "}
              <span
                className={
                  statusQuery.data.lab_api_auth_enabled !== false ? "text-amber-200" : "text-emerald-300"
                }
              >
                {statusQuery.data.lab_api_auth_enabled === false ? "no (dev only)" : "yes"}
              </span>
            </li>
            <li>
              <code className="text-xs">LAB_API_TOKEN</code> on API host:{" "}
              <span
                className={
                  statusQuery.data.lab_api_token_configured ? "text-emerald-300" : "text-muted"
                }
              >
                {statusQuery.data.lab_api_token_configured ? "set" : "not set (ephemeral token may be logged at API startup)"}
              </span>
            </li>
            <li>
              <code className="text-xs">NEXT_PUBLIC_LAB_API_TOKEN</code> in UI build:{" "}
              <span className={labUiTokenConfigured ? "text-emerald-300" : "text-muted"}>
                {labUiTokenConfigured ? "set" : "not set"}
              </span>
            </li>
          </ul>
        )}
        {statusQuery.data?.lab_api_auth_enabled !== false && !labUiTokenConfigured && (
          <p className="mt-3 text-sm text-amber-200/90">
            Add the same token to <code className="text-xs">apps/lab-ui/.env.local</code> as{" "}
            <code className="text-xs">NEXT_PUBLIC_LAB_API_TOKEN</code>, then restart{" "}
            <code className="text-xs">./run-lab-ui.sh</code>. Without it, job launches and Settings
            credential saves return 401.
          </p>
        )}
      </Card>

      <Card title="Exchange status">
        {statusQuery.isLoading && (
          <div className="space-y-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-4 w-3/5" />
          </div>
        )}
        {statusQuery.isError && <ErrorState title="Could not read credential status" error={statusQuery.error} />}
        {statusQuery.data && (
          <ul className="text-sm space-y-1 text-slate-200">
            <li>
              API keys in .env:{" "}
              <span className={statusQuery.data.api_keys_configured ? "text-emerald-300" : "text-muted"}>
                {statusQuery.data.api_keys_configured ? "yes" : "no"}
              </span>
            </li>
            <li>
              Session token in .env:{" "}
              <span className={statusQuery.data.auth_token_configured ? "text-emerald-300" : "text-muted"}>
                {statusQuery.data.auth_token_configured ? "yes" : "no"}
              </span>
            </li>
            <li>
              Hyperliquid wallet:{" "}
              <span
                className={
                  statusQuery.data.hyperliquid_wallet_configured ? "text-emerald-300" : "text-muted"
                }
              >
                {statusQuery.data.hyperliquid_wallet_configured ? "yes" : "no"}
              </span>
            </li>
            <li>
              Hyperliquid trading key:{" "}
              <span
                className={
                  statusQuery.data.hyperliquid_trading_configured ? "text-emerald-300" : "text-muted"
                }
              >
                {statusQuery.data.hyperliquid_trading_configured ? "yes" : "no"}
              </span>
            </li>
          </ul>
        )}
      </Card>

      <Card
        title="Hyperliquid"
        description="Wallet address for charts and account state; private key required for live perp orders."
      >
        {hyperliquidQuery.data && <JsonBlock value={hyperliquidQuery.data} />}
        <form
          className="mt-4 space-y-3 max-w-md"
          onSubmit={(event) => {
            event.preventDefault();
            saveHyperliquidMutation.mutate();
          }}
        >
          <Field label="Wallet address (0x…)">
            <TextInput
              value={hlWallet}
              onChange={(event) => setHlWallet(event.target.value)}
              placeholder="0x…"
              autoComplete="off"
            />
          </Field>
          <Field label="Private key (optional, for live orders)" hint="Never committed to git — stored in .env only.">
            <TextInput
              type="password"
              value={hlPrivateKey}
              onChange={(event) => setHlPrivateKey(event.target.value)}
              autoComplete="off"
            />
          </Field>
          {saveHyperliquidMutation.isError && (
            <p className="text-sm text-red-400">
              {saveHyperliquidMutation.error instanceof Error
                ? saveHyperliquidMutation.error.message
                : "Save failed."}
            </p>
          )}
          {saveHyperliquidMutation.isSuccess && (
            <p className="text-sm text-emerald-300/90">Saved to .env on the Lab API host.</p>
          )}
          <Button type="submit" disabled={saveHyperliquidMutation.isPending || !hlWallet.trim()}>
            Save Hyperliquid credentials
          </Button>
        </form>
      </Card>

      {statusQuery.data?.api_keys_configured && (
        <Card title="Profile (API key)">
          {profileQuery.isLoading && <Skeleton className="h-16" />}
          {profileQuery.isError && (
            <p className="text-sm text-red-400">
              {profileQuery.error instanceof Error ? profileQuery.error.message : "Profile failed."}
            </p>
          )}
          {profileQuery.data && <JsonBlock value={profileQuery.data} />}
        </Card>
      )}

      <Card title="Session login" description="Stores NOBITEX_AUTH_TOKEN in .env when successful.">
        <form
          className="space-y-3 max-w-md"
          onSubmit={(event) => {
            event.preventDefault();
            loginMutation.mutate();
          }}
        >
          <Field label="Email">
            <TextInput value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </Field>
          <Field label="Password">
            <TextInput
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </Field>
          <Field label="2FA (optional)">
            <TextInput value={totp} onChange={(e) => setTotp(e.target.value)} placeholder="6-digit TOTP" />
          </Field>
          {loginMutation.isError && (
            <p className="text-sm text-red-400">
              {loginMutation.error instanceof Error ? loginMutation.error.message : "Login failed."}
            </p>
          )}
          {loginMutation.isSuccess && (
            <p className="text-sm text-emerald-300/90">Login submitted — check status above.</p>
          )}
          <Button type="submit" disabled={loginMutation.isPending || !username || !password}>
            Login & save token
          </Button>
        </form>
      </Card>

      <Card
        title="Create API key"
        description="Requires session token in .env. Private keys are stored server-side in .env only — never returned to the browser."
      >
        <form
          className="space-y-3 max-w-md"
          onSubmit={(event) => {
            event.preventDefault();
            createKeyMutation.mutate();
          }}
        >
          <Field label="Key name">
            <TextInput value={keyName} onChange={(e) => setKeyName(e.target.value)} />
          </Field>
          <Field label="2FA (required)">
            <TextInput value={createTotp} onChange={(e) => setCreateTotp(e.target.value)} />
          </Field>
          {createKeyMutation.isError && (
            <p className="text-sm text-red-400">
              {createKeyMutation.error instanceof Error ? createKeyMutation.error.message : "Create failed."}
            </p>
          )}
          {createKeyMutation.data && <JsonBlock value={createKeyMutation.data} />}
          <Button type="submit" disabled={createKeyMutation.isPending || !createTotp}>
            Create API key
          </Button>
        </form>
      </Card>

      {statusQuery.data?.auth_token_configured && keysQuery.data !== undefined && (
        <Card title="API keys (session)">
          <JsonBlock value={keysQuery.data} />
        </Card>
      )}
    </div>
  );
}
