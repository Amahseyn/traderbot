"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { PageHeader } from "@/components/ui/PageHeader";
import { api } from "@/lib/api";

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const statusQuery = useQuery({ queryKey: ["auth-status"], queryFn: api.authStatus });

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [keyName, setKeyName] = useState("traderbot-lab");
  const [createTotp, setCreateTotp] = useState("");

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
    <div className="space-y-8">
      <PageHeader
        title="Nobitex & credentials"
        description="Session login and API keys are written to the repo .env on the machine running the Lab API (local research only)."
      />

      <Card title="Status">
        {statusQuery.isLoading && <p className="text-sm text-muted">Checking…</p>}
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
          </ul>
        )}
      </Card>

      {statusQuery.data?.api_keys_configured && (
        <Card title="Profile (API key)">
          {profileQuery.isLoading && <p className="text-sm text-muted">Loading profile…</p>}
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
