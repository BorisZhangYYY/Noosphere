import { useEffect, useState } from "react";
import { ReviewPlayback } from "./reviewPlayback";
import type { ReviewJob } from "./types";

const players = new Map<string, ReviewPlayback>();

export function useReviewPreview(job: ReviewJob | null | undefined, starting: boolean) {
  const [frame, setFrame] = useState({ id: "", text: "", pending: false });
  const active = Boolean(job && ["queued", "running"].includes(job.status));
  const discarded = job?.status === "cancelled" || job?.status === "failed";
  const text = job?.reviewPreview ?? "";
  useEffect(() => {
    if (!job || discarded) {
      if (job) players.delete(job.id);
      setFrame({ id: "", text: "", pending: false });
      return;
    }
    let player = players.get(job.id);
    if (!player) {
      player = new ReviewPlayback(text, !active);
      players.set(job.id, player);
      if (players.size > 100) players.delete(players.keys().next().value!);
    }
    player.update(text, performance.now());
    let request = 0;
    const step = (now: number) => {
      setFrame({ id: job.id, text: player.frame(now), pending: player.pending });
      if (player.pending) request = requestAnimationFrame(step);
    };
    step(performance.now());
    return () => cancelAnimationFrame(request);
  }, [job?.id, text, active, discarded]);
  const current = frame.id === job?.id && !discarded;
  return {
    visible: starting ? "" : current ? frame.text : "",
    showing: starting || (!discarded && (active || (current && (frame.pending || frame.text !== text)))),
    active
  };
}
