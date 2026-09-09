"use client";

import { Download, Loader2, RefreshCw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { client } from "@/client/client.gen";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAuth } from "@/lib/auth";

import type { PocCallList } from "./types";

const engines = ["", "openai_realtime", "gemini_live", "google_cascade"];
const outcomes = ["", "ticket_created", "resolved", "transferred", "failed", "unknown"];

function endOfDay(value: string) {
  return value ? new Date(`${value}T23:59:59.999`).toISOString() : undefined;
}

export default function PocCallsPage() {
  const auth = useAuth();
  const [data, setData] = useState<PocCallList>({ items: [], total: 0 });
  const [loading, setLoading] = useState(false);
  const [engine, setEngine] = useState("");
  const [outcome, setOutcome] = useState("");
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<number[]>([]);

  const query = useCallback(
    () => ({
      ...(engine && { engine }),
      ...(outcome && { outcome }),
      ...(createdFrom && {
        created_from: new Date(`${createdFrom}T00:00:00`).toISOString(),
      }),
      ...(createdTo && { created_to: endOfDay(createdTo) }),
      ...(search && { search }),
    }),
    [createdFrom, createdTo, engine, outcome, search],
  );

  const load = useCallback(async () => {
    if (!auth.isAuthenticated) return;
    setLoading(true);
    try {
      const response = await client.get<{ 200: PocCallList }, unknown, true>({
        url: "/api/v1/poc/calls",
        query: query(),
        throwOnError: true,
      });
      setData(response.data ?? { items: [], total: 0 });
      setSelected([]);
    } catch {
      toast.error("Could not load POC calls");
    } finally {
      setLoading(false);
    }
  }, [auth.isAuthenticated, query]);

  useEffect(() => {
    void load();
  }, [load]);

  const removeSelected = async () => {
    if (
      !selected.length ||
      !window.confirm(
        `Delete ${selected.length} selected call(s) and their Asterisk recordings?`,
      )
    )
      return;
    try {
      await client.delete<unknown, unknown, true>({
        url: "/api/v1/poc/calls",
        body: { run_ids: selected },
        throwOnError: true,
      });
      toast.success("Selected calls deleted");
      await load();
    } catch {
      toast.error("Could not delete selected calls");
    }
  };

  const removeAll = async () => {
    try {
      const allCalls = await client.get<{ 200: PocCallList }, unknown, true>({
        url: "/api/v1/poc/calls",
        query: { limit: 1 },
        throwOnError: true,
      });
      const total = allCalls.data?.total ?? 0;
      if (!total) {
        toast.info("There are no POC calls to delete");
        return;
      }
      if (
        !window.confirm(
          `Permanently delete all ${total} POC calls and their Asterisk recordings?`,
        )
      )
        return;
      const response = await client.delete<
        { 200: { deleted: number } },
        unknown,
        true
      >({
        url: "/api/v1/poc/calls/all",
        throwOnError: true,
      });
      toast.success(`${response.data?.deleted ?? 0} calls deleted`);
      await load();
    } catch {
      toast.error("Could not delete all POC calls");
    }
  };

  const downloadCsv = async () => {
    try {
      const response = await client.get<{ 200: Blob }, unknown, true>({
        url: "/api/v1/poc/calls/export.csv",
        query: query(),
        parseAs: "blob",
        throwOnError: true,
      });
      if (!response.data) return;
      const url = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = url;
      link.download = "poc-calls.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Could not export CSV");
    }
  };

  if (auth.loading)
    return (
      <div className="flex min-h-64 items-center justify-center">
        <Loader2 className="animate-spin" />
      </div>
    );

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">AI receptionist POC calls</h1>
          <p className="text-sm text-muted-foreground">
            Private, organization-scoped call runs and recordings.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => void downloadCsv()}>
            <Download className="mr-2 h-4 w-4" />CSV
          </Button>
          <Button variant="outline" onClick={() => void load()}>
            <RefreshCw className="mr-2 h-4 w-4" />Refresh
          </Button>
          <Button
            variant="destructive"
            disabled={!selected.length}
            onClick={() => void removeSelected()}
          >
            <Trash2 className="mr-2 h-4 w-4" />Delete selected
          </Button>
          <Button
            variant="destructive"
            onClick={() => void removeAll()}
          >
            <Trash2 className="mr-2 h-4 w-4" />Delete all
          </Button>
        </div>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{data.total} calls</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-3">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Run, caller, or ticket"
              className="max-w-xs"
            />
            <select
              className="rounded-md border bg-background px-3 text-sm"
              value={engine}
              onChange={(event) => setEngine(event.target.value)}
            >
              {engines.map((item) => (
                <option key={item} value={item}>{item || "All engines"}</option>
              ))}
            </select>
            <select
              className="rounded-md border bg-background px-3 text-sm"
              value={outcome}
              onChange={(event) => setOutcome(event.target.value)}
            >
              {outcomes.map((item) => (
                <option key={item} value={item}>{item || "All outcomes"}</option>
              ))}
            </select>
            <Input aria-label="Calls from" type="date" value={createdFrom} onChange={(event) => setCreatedFrom(event.target.value)} className="w-auto" />
            <Input aria-label="Calls through" type="date" value={createdTo} onChange={(event) => setCreatedTo(event.target.value)} className="w-auto" />
          </div>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10" /><TableHead>Started</TableHead><TableHead>Engine / models</TableHead><TableHead>Language</TableHead><TableHead>Caller</TableHead><TableHead>Duration</TableHead><TableHead>Outcome</TableHead><TableHead>Ticket</TableHead><TableHead>List cost</TableHead><TableHead>Actual est.</TableHead><TableHead>First response</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow><TableCell colSpan={11} className="text-center">Loading…</TableCell></TableRow>
                ) : data.items.map((call) => (
                  <TableRow key={call.id}>
                    <TableCell><input aria-label={`Select call ${call.id}`} type="checkbox" checked={selected.includes(call.id)} onChange={(event) => setSelected(event.target.checked ? [...selected, call.id] : selected.filter((id) => id !== call.id))} /></TableCell>
                    <TableCell><Link className="font-medium text-primary hover:underline" href={`/poc/calls/${call.id}`}>{new Date(call.created_at).toLocaleString()}</Link></TableCell>
                    <TableCell><div>{call.engine}</div><div className="max-w-56 text-xs text-muted-foreground">{call.models}</div></TableCell>
                    <TableCell>{call.language}</TableCell>
                    <TableCell>{call.caller}</TableCell>
                    <TableCell>{call.duration_seconds}s</TableCell>
                    <TableCell><Badge variant="secondary">{call.outcome}</Badge></TableCell>
                    <TableCell>{call.ticket_number ?? "—"}</TableCell>
                    <TableCell>{call.normalized_list_cost_usd == null ? "—" : `$${call.normalized_list_cost_usd.toFixed(4)}`}</TableCell>
                    <TableCell>{call.actual_billed_estimate_usd == null ? "—" : `$${call.actual_billed_estimate_usd.toFixed(4)}`}</TableCell>
                    <TableCell>{call.first_response_latency_ms == null ? "—" : `${call.first_response_latency_ms.toFixed(0)}ms`}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
