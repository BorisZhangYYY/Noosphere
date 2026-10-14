import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type DragEvent, type KeyboardEvent } from "react";
import { api } from "../api";
import { canReorderWorkspace, type WorkspaceEntry } from "../workspaceOrder";

type DragEntry = WorkspaceEntry & { name: string };
type Target = WorkspaceEntry & { side: "before" | "after"; blocked: boolean };

export function useWorkspaceOrdering(disabled = false) {
  const queryClient = useQueryClient();
  const [drag, setDrag] = useState<DragEntry | null>(null);
  const [target, setTarget] = useState<Target | null>(null);
  const [error, setError] = useState("");
  const finish = () => { setDrag(null); setTarget(null); };
  const refresh = () => Promise.all([
    queryClient.invalidateQueries({ queryKey: ["collections"] }),
    queryClient.invalidateQueries({ queryKey: ["articles"] })
  ]);
  const mutation = useMutation({
    mutationFn: api.reorderWorkspace,
    onSuccess: async () => { setError(""); await refresh(); },
    onError: async (failure: Error) => { setError(failure.message); await refresh(); }
  });
  useEffect(() => {
    const cancel = (event: globalThis.KeyboardEvent) => { if (event.key === "Escape") finish(); };
    window.addEventListener("keydown", cancel);
    window.addEventListener("blur", finish);
    return () => { window.removeEventListener("keydown", cancel); window.removeEventListener("blur", finish); };
  }, []);
  useEffect(() => {
    if (!drag) return;
    const guard = (event: globalThis.DragEvent) => {
      if (event.target instanceof Element && event.target.closest("[data-workspace-order-entry]")) return;
      event.preventDefault(); event.stopImmediatePropagation();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "none";
      if (event.type === "drop") finish();
      else setTarget({ ...drag, id: "", side: "before", blocked: true });
    };
    document.addEventListener("dragover", guard, true);
    document.addEventListener("drop", guard, true);
    return () => { document.removeEventListener("dragover", guard, true); document.removeEventListener("drop", guard, true); };
  }, [drag]);

  const row = (entry: WorkspaceEntry, name: string, siblings: string[]) => {
    const allowed = Boolean(drag && canReorderWorkspace(drag, entry));
    const sameScope = drag?.kind === entry.kind && drag.scopeId === entry.scopeId;
    const hovered = target?.id === entry.id && target.kind === entry.kind;
    const className = [
      drag?.id === entry.id && drag.kind === entry.kind ? "workspace-order-dragging" : "",
      drag && (drag.kind !== entry.kind || drag.scopeId !== entry.scopeId) ? "workspace-order-unavailable" : "",
      hovered ? target.blocked ? "workspace-order-blocked" : `workspace-order-${target.side}` : ""
    ].filter(Boolean).join(" ");
    const destination = (event: DragEvent<HTMLElement>) => {
      const bounds = event.currentTarget.getBoundingClientRect();
      return event.clientY < bounds.top + bounds.height / 2 ? "before" : "after";
    };
    return {
      className,
      "data-workspace-order-entry": entry.kind,
      onDragStart: (event: DragEvent<HTMLElement>) => {
        if (disabled || mutation.isPending) { event.preventDefault(); return; }
        event.stopPropagation();
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("application/x-noosphere-workspace-order", JSON.stringify(entry));
        event.dataTransfer.setData("text/plain", name);
        setDrag({ ...entry, name }); setTarget(null); setError("");
      },
      onDragOver: (event: DragEvent<HTMLElement>) => {
        if (!drag) return;
        event.preventDefault(); event.stopPropagation();
        // The original row is a valid no-op destination during native drag startup.
        event.dataTransfer.dropEffect = sameScope ? "move" : "none";
        if (drag.id === entry.id && drag.kind === entry.kind) { setTarget(null); return; }
        setTarget({ ...entry, side: destination(event), blocked: !allowed });
      },
      onDrop: (event: DragEvent<HTMLElement>) => {
        if (!drag) return;
        event.preventDefault(); event.stopPropagation();
        if (allowed && !disabled && !mutation.isPending) {
          mutation.mutate({ kind: entry.kind, sourceId: drag.id, targetId: entry.id, scopeId: entry.scopeId, side: destination(event) });
        }
        finish();
      },
      onDragEnd: finish,
      onKeyDown: (event: KeyboardEvent<HTMLElement>) => {
        if (!event.altKey || event.nativeEvent.isComposing || !["ArrowUp", "ArrowDown"].includes(event.key)) return;
        event.preventDefault(); event.stopPropagation();
        if (disabled || mutation.isPending) return;
        const targetId = siblings[siblings.indexOf(entry.id) + (event.key === "ArrowUp" ? -1 : 1)];
        if (!targetId) return;
        setError("");
        mutation.mutate({ kind: entry.kind, sourceId: entry.id, targetId, scopeId: entry.scopeId, side: event.key === "ArrowUp" ? "before" : "after" });
      }
    };
  };
  const scopeClass = (kind: WorkspaceEntry["kind"], scopeId: string | null) =>
    drag?.kind === kind && drag.scopeId === scopeId ? "workspace-order-allowed-scope" : "";
  return { row, scopeClass, drag, target, error, isPending: mutation.isPending };
}

export type WorkspaceOrdering = ReturnType<typeof useWorkspaceOrdering>;
