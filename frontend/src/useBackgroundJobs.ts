import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { BackgroundJob } from "./types";

export const backgroundJobsKey = ["background-jobs"] as const;

export function useBackgroundJobSync() {
  const client = useQueryClient();
  const [connected, setConnected] = useState(false);
  const query = useQuery({
    queryKey: backgroundJobsKey,
    queryFn: api.listBackgroundJobs,
    refetchInterval: connected ? false : 1500
  });
  const previous = useRef(new Map<string, string>());

  useEffect(() => {
    let refresh = false;
    const states = new Map<string, string>();
    for (const job of query.data?.jobs ?? []) {
      const state = `${job.status}:${job.articleId ?? ""}`;
      if (previous.current.get(job.id) !== state) {
        refresh = true;
        if (job.articleId) void client.invalidateQueries({ queryKey: ["article", job.articleId] });
      }
      states.set(job.id, state);
    }
    previous.current = states;
    if (refresh) {
      void client.invalidateQueries({ queryKey: ["articles"] });
      void client.invalidateQueries({ queryKey: ["collections"] });
    }
  }, [client, query.data]);

  useEffect(() => {
    let mounted = true;
    const stream = new EventSource("/api/v1/jobs/stream");
    stream.onerror = () => setConnected(false);
    stream.addEventListener("jobs", async event => {
      try {
        const update = JSON.parse((event as MessageEvent).data) as {
          reset: boolean; jobs: BackgroundJob[]; removedIds: string[];
        };
        await client.cancelQueries({ queryKey: backgroundJobsKey });
        if (!mounted) return;
        setConnected(true);
        client.setQueryData<{ jobs: BackgroundJob[] }>(backgroundJobsKey, current => {
          const jobs = new Map((update.reset ? [] : current?.jobs ?? []).map(job => [job.id, job]));
          update.removedIds.forEach(id => jobs.delete(id));
          update.jobs.forEach(job => jobs.set(job.id, job));
          return { jobs: [...jobs.values()].sort((left, right) => right.createdAt.localeCompare(left.createdAt)) };
        });
      } catch {
        void client.invalidateQueries({ queryKey: backgroundJobsKey });
      }
    });
    return () => { mounted = false; stream.close(); };
  }, [client]);
}
