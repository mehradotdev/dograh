"use client";

import { ArrowLeft, ExternalLink, Loader2, Play, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { client } from "@/client/client.gen";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth";

import type { PocCallDetail } from "../types";

function JsonPanel({ title, value }: { title: string; value: unknown }) {
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">{title}</CardTitle></CardHeader>
      <CardContent>
        <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-4 text-xs">
          {JSON.stringify(value, null, 2)}
        </pre>
      </CardContent>
    </Card>
  );
}

function Fact({ label, value }: { label: string; value: string | number | null }) {
  return <div><div className="text-xs text-muted-foreground">{label}</div>{value ?? "—"}</div>;
}

export default function PocCallDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const auth = useAuth();
  const router = useRouter();
  const [call, setCall] = useState<PocCallDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!auth.isAuthenticated) return;
    try {
      const response = await client.get<{ 200: PocCallDetail }, unknown, true>({
        url: `/api/v1/poc/calls/${runId}`,
        throwOnError: true,
      });
      setCall(response.data ?? null);
    } catch {
      toast.error("Could not load this POC call");
    } finally {
      setLoading(false);
    }
  }, [auth.isAuthenticated, runId]);

  useEffect(() => {
    void load();
  }, [load]);
  useEffect(
    () => () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    },
    [audioUrl],
  );

  const loadRecording = async () => {
    try {
      const response = await client.get<{ 200: Blob }, unknown, true>({
        url: `/api/v1/poc/calls/${runId}/recording`,
        parseAs: "blob",
        throwOnError: true,
      });
      if (response.data) setAudioUrl(URL.createObjectURL(response.data));
    } catch {
      toast.error("Recording is unavailable");
    }
  };

  const openDograhArtifact = async (key: string) => {
    try {
      const response = await client.get<
        { 200: { url: string; expires_in: number } },
        unknown,
        true
      >({
        url: "/api/v1/s3/signed-url",
        query: { key, inline: true },
        throwOnError: true,
      });
      if (response.data?.url) {
        const link = document.createElement("a");
        link.href = response.data.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.click();
      }
    } catch {
      toast.error("Artifact is unavailable");
    }
  };

  const remove = async () => {
    if (!window.confirm("Delete this call run and its Asterisk recording?")) return;
    try {
      await client.delete<unknown, unknown, true>({
        url: `/api/v1/poc/calls/${runId}`,
        throwOnError: true,
      });
      router.push("/poc/calls");
    } catch {
      toast.error("Could not delete the call");
    }
  };

  if (auth.loading || loading)
    return <div className="flex min-h-64 items-center justify-center"><Loader2 className="animate-spin" /></div>;
  if (!call) return <div className="p-6">Call not found.</div>;

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <Button asChild variant="ghost" className="mb-2 px-0"><Link href="/poc/calls"><ArrowLeft className="mr-2 h-4 w-4" />All POC calls</Link></Button>
          <h1 className="text-2xl font-semibold">Call #{call.id}</h1>
          <div className="mt-2 flex gap-2"><Badge>{call.engine}</Badge><Badge variant="secondary">{call.outcome}</Badge></div>
        </div>
        <Button variant="destructive" onClick={() => void remove()}><Trash2 className="mr-2 h-4 w-4" />Delete</Button>
      </div>
      <Card>
        <CardHeader><CardTitle className="text-base">Call evidence</CardTitle></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3 lg:grid-cols-5">
          <Fact label="Started" value={new Date(call.created_at).toLocaleString()} />
          <Fact label="Asterisk call ID" value={call.asterisk_call_id} />
          <Fact label="Incoming caller" value={call.caller_number} />
          <Fact label="Normalized E.164" value={call.caller_e164} />
          <Fact label="WFMS mobile" value={call.wfms_mobile} />
          <Fact label="Models" value={call.models} />
          <Fact label="Language" value={call.language} />
          <Fact label="Duration" value={`${call.duration_seconds}s`} />
          <Fact label="First response" value={call.first_response_latency_ms == null ? null : `${call.first_response_latency_ms.toFixed(0)}ms`} />
          <Fact label="Ticket" value={call.ticket_number} />
          <Fact label="Normalized list cost" value={call.normalized_list_cost_usd == null ? null : `$${call.normalized_list_cost_usd.toFixed(6)}`} />
          <Fact label="Actual estimate" value={call.actual_billed_estimate_usd == null ? null : `$${call.actual_billed_estimate_usd.toFixed(6)}`} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">Recordings and transcript</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {audioUrl ? <audio controls className="w-full" src={audioUrl} /> : <Button variant="outline" disabled={!call.recording_available} onClick={() => void loadRecording()}><Play className="mr-2 h-4 w-4" />{call.recording_available ? "Load full Asterisk recording" : "Asterisk recording unavailable"}</Button>}
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" disabled={!call.transcript_url} onClick={() => call.transcript_url && void openDograhArtifact(call.transcript_url)}><ExternalLink className="mr-2 h-4 w-4" />Open transcript</Button>
            <Button variant="outline" disabled={!call.dograh_recording_url} onClick={() => call.dograh_recording_url && void openDograhArtifact(call.dograh_recording_url)}><ExternalLink className="mr-2 h-4 w-4" />Open Dograh recording</Button>
          </div>
        </CardContent>
      </Card>
      <div className="grid gap-6 lg:grid-cols-2">
        <JsonPanel title="Runtime stack" value={call.runtime_configuration} />
        <JsonPanel title="Usage and model metrics" value={call.usage_info} />
        <JsonPanel title="Cost breakdown and pricing version" value={call.cost_info} />
        <JsonPanel title="Tool calls, WFMS timing, classification, and outcome" value={call.gathered_context} />
        <JsonPanel title="Latency, errors, and retries" value={call.logs} />
        <JsonPanel title="Call context" value={call.initial_context} />
      </div>
    </div>
  );
}
