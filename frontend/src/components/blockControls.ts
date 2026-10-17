import { nearestDragBlock } from "../imageDrag";
import { articleNodeAtPath, articleNodePath, isMovableArticleBlock, outerArticleList } from "../blockDrag";

interface Point { x: number; y: number }
interface HoverRow { node: HTMLElement; top: number; bottom: number; left: number }
export const GRIP_SVG = '<svg viewBox="0 0 12 18" width="12" height="18" fill="currentColor" aria-hidden="true"><circle cx="3" cy="3" r="1.5"/><circle cx="9" cy="3" r="1.5"/><circle cx="3" cy="9" r="1.5"/><circle cx="9" cy="9" r="1.5"/><circle cx="3" cy="15" r="1.5"/><circle cx="9" cy="15" r="1.5"/></svg>';
const GROUP_GRIP_SVG = '<svg viewBox="0 0 18 18" width="18" height="18" fill="currentColor" aria-hidden="true"><path d="M4 1.5H1.5v15H4M14 1.5h2.5v15H14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round"/><circle cx="6" cy="4" r="1.25"/><circle cx="12" cy="4" r="1.25"/><circle cx="6" cy="9" r="1.25"/><circle cx="12" cy="9" r="1.25"/><circle cx="6" cy="14" r="1.25"/><circle cx="12" cy="14" r="1.25"/></svg>';
interface BlockControlsOptions {
  host: HTMLElement;
  frame: HTMLElement;
  layer: HTMLElement;
  root: () => HTMLElement | null;
  readOnly: () => boolean;
  isDragging: () => boolean;
  labels: { handle: string; up: string; down: string; wholeList: string; listItem: string;
    heading: string; section: string; fold: string; unfold: string };
  neighbor: (block: HTMLElement, direction: "before" | "after") => HTMLElement | null;
  canFold: (block: HTMLElement) => boolean;
  isFolded: (block: HTMLElement) => boolean;
  toggleFold: (block: HTMLElement) => void;
  begin: (block: HTMLElement, point: Point) => boolean;
  update: (point: Point) => void;
  finish: (point: Point) => void;
  cancel: () => void;
  move: (block: HTMLElement, direction: "before" | "after") => HTMLElement | null;
}

export function installBlockControls(options: BlockControlsOptions) {
  const { host, frame, layer } = options;
  const reader = frame.closest<HTMLElement>(".reader-surface") ?? frame;
  const controls = document.createElement("div");
  controls.className = "noosphere-block-controls";
  controls.hidden = true;
  const handle = document.createElement("button");
  handle.type = "button";
  handle.className = "noosphere-block-handle";
  handle.innerHTML = GRIP_SVG;
  handle.setAttribute("aria-label", options.labels.handle);
  handle.title = options.labels.handle;
  handle.setAttribute("aria-expanded", "false");
  const directions = document.createElement("div");
  directions.className = "noosphere-block-directions";
  directions.hidden = true;
  const up = document.createElement("button"), down = document.createElement("button");
  for (const [button, label, symbol] of [[up, options.labels.up, "↑"], [down, options.labels.down, "↓"]] as const) {
    button.type = "button";
    button.setAttribute("aria-label", label);
    button.title = label;
    button.textContent = symbol;
    button.onpointerdown = event => event.preventDefault();
    directions.append(button);
  }
  const containerHandle = document.createElement("button");
  containerHandle.type = "button";
  containerHandle.className = "noosphere-container-handle";
  containerHandle.setAttribute("aria-label", options.labels.wholeList);
  containerHandle.title = options.labels.wholeList;
  containerHandle.hidden = true;
  containerHandle.innerHTML = GROUP_GRIP_SVG;
  const fold = document.createElement("button");
  fold.type = "button";
  fold.className = "noosphere-heading-toggle";
  fold.hidden = true;
  fold.onpointerdown = event => event.preventDefault();
  controls.append(containerHandle, handle, fold, directions);
  const boundary = document.createElement("div");
  boundary.className = "noosphere-block-boundary";
  boundary.setAttribute("aria-hidden", "true");
  boundary.hidden = true;
  const markerMeasure = document.createElement("span");
  markerMeasure.setAttribute("aria-hidden", "true");
  markerMeasure.style.cssText = "position:absolute;visibility:hidden;white-space:pre;pointer-events:none";
  layer.append(boundary, controls, markerMeasure);
  let block: HTMLElement | null = null;
  let blockPath: number[] | null = null;
  let wholeList = false;
  const activeHandle = () => wholeList ? containerHandle : handle;
  const activeBlock = () => wholeList && block ? outerArticleList(block, options.root()!) : block;
  let pointer: { id: number; start: Point; started: boolean; owner: HTMLButtonElement; source: HTMLElement } | null = null;
  let suppressClick = false;
  let leaveTimer = 0;
  let hoverRows: HoverRow[] | null = null;
  let marginBounds: DOMRect | null = null;
  let mousePoint: Point | null = null;
  const invalidateLayout = () => { hoverRows = null; };
  const clearLeave = () => { window.clearTimeout(leaveTimer); leaveTimer = 0; };

  const expand = (open: boolean) => {
    directions.hidden = !open;
    handle.setAttribute("aria-expanded", String(open && !wholeList));
    containerHandle.setAttribute("aria-expanded", String(open && wholeList));
  };
  const refresh = () => {
    const root = options.root();
    if (options.readOnly() || !root) {
      if (pointer) cancel();
      controls.hidden = true;
      boundary.hidden = true;
      expand(false);
      return;
    }
    if (pointer?.started) return;
    // Vditor may replace the same content after a touch caret update.
    if (block && !root.contains(block) && blockPath) block = articleNodeAtPath(root, blockPath);
    if (!isMovableArticleBlock(block, root) || options.isDragging()) {
      controls.hidden = true;
      boundary.hidden = true;
      return;
    }
    if (block.tagName !== "LI") wholeList = false;
    const source = activeBlock()!;
    const bounds = block.getBoundingClientRect(), frameBounds = frame.getBoundingClientRect();
    let left = bounds.left;
    if (block.tagName === "LI" && block.parentElement) {
      // Outside list markers are excluded from the item's bounding rectangle.
      const list = block.parentElement;
      left = list.getBoundingClientRect().left;
      if (list instanceof HTMLOListElement) {
        const markerStyle = getComputedStyle(block, "::marker");
        for (const property of ["fontFamily", "fontSize", "fontStyle", "fontWeight", "fontStretch", "fontVariant", "fontFeatureSettings", "fontVariationSettings", "letterSpacing"] as const) {
          markerMeasure.style[property] = markerStyle[property];
        }
        const index = Array.from(list.children).indexOf(block);
        const number = (block as HTMLLIElement).hasAttribute("value") ? (block as HTMLLIElement).value
          : list.start + index * (list.reversed ? -1 : 1);
        markerMeasure.textContent = `${number}.\u00a0`;
        const width = markerMeasure.getBoundingClientRect().width + parseFloat(markerStyle.fontSize) * .25;
        left = Math.min(left, bounds.left - width);
      }
    }
    const list = block.tagName === "LI" ? outerArticleList(block, root) : null;
    const heading = /^H[1-6]$/.test(block.tagName);
    const rootBounds = root.getBoundingClientRect();
    const controlLeft = Math.max(reader.getBoundingClientRect().left + 4,
      rootBounds.left + parseFloat(getComputedStyle(root).paddingLeft) - 48);
    controls.hidden = !bounds.height;
    controls.style.left = `${controlLeft - frameBounds.left}px`;
    controls.style.top = `${bounds.top - frameBounds.top}px`;
    containerHandle.hidden = !list;
    handle.style.gridColumn = list ? "2" : "1";
    fold.hidden = !heading || !options.canFold(block);
    const folded = options.isFolded(block);
    fold.textContent = folded ? "▸" : "▾";
    fold.setAttribute("aria-expanded", String(!folded));
    fold.setAttribute("aria-label", folded ? options.labels.unfold : options.labels.fold);
    fold.title = folded ? options.labels.unfold : options.labels.fold;
    const label = list ? options.labels.listItem : heading ? folded ? options.labels.section : options.labels.heading : options.labels.handle;
    handle.setAttribute("aria-label", label);
    handle.title = label;
    const selectedBounds = source.getBoundingClientRect();
    const boundaryLeft = wholeList ? selectedBounds.left : left;
    boundary.hidden = !selectedBounds.height;
    boundary.style.left = `${boundaryLeft - frameBounds.left - 3}px`;
    boundary.style.top = `${selectedBounds.top - frameBounds.top}px`;
    boundary.style.width = `${selectedBounds.right - boundaryLeft + 6}px`;
    boundary.style.height = `${selectedBounds.height}px`;
    directions.style.left = `${list && !wholeList ? 22 : 0}px`;
    up.disabled = !options.neighbor(source, "before");
    down.disabled = !options.neighbor(source, "after");
    expand(!directions.hidden);
  };
  const show = (node: HTMLElement | null) => {
    const root = options.root();
    if (!root || !isMovableArticleBlock(node, root)) return;
    if (["UL", "OL"].includes(node.tagName)) node = node.querySelector<HTMLElement>("li") ?? node;
    if (block !== node) { wholeList = false; expand(false); }
    block = node;
    blockPath = articleNodePath(root, node);
    refresh();
  };
  const selectFrom = (node: Node | null) => {
    const root = options.root();
    let element = node instanceof HTMLElement ? node : node?.parentElement;
    const item = element?.closest<HTMLElement>("li");
    if (root && item && isMovableArticleBlock(item, root)) return item;
    while (element && element.parentElement !== root) element = element.parentElement;
    return root && isMovableArticleBlock(element ?? null, root) ? element ?? null : null;
  };
  const marginTarget = (point: Point): HTMLElement | null | undefined => {
    const root = options.root();
    if (!root) return undefined;
    if (!hoverRows) {
      const rows: HoverRow[] = [];
      for (const node of Array.from(root.children)) {
        if (!(node instanceof HTMLElement)) continue;
        const bounds = node.getBoundingClientRect();
        if (!bounds.height || !bounds.width) continue;
        if (!["UL", "OL"].includes(node.tagName)) {
          rows.push({ node, top: bounds.top, bottom: bounds.bottom, left: bounds.left });
          continue;
        }
        for (const item of Array.from(node.querySelectorAll<HTMLElement>("li"))) {
          const itemBounds = item.getBoundingClientRect();
          if (!itemBounds.height) continue;
          // Exclude nested-list spans so their rows remain selectable from the outer margin.
          let top = itemBounds.top;
          const childLists = Array.from(item.children).filter(child => ["UL", "OL"].includes(child.tagName));
          for (const child of childLists) {
            const childBounds = child.getBoundingClientRect();
            if (!childBounds.height) continue;
            if (childBounds.top > top) rows.push({ node: item, top, bottom: childBounds.top, left: itemBounds.left });
            top = childBounds.bottom;
          }
          if (itemBounds.bottom > top) rows.push({ node: item, top, bottom: itemBounds.bottom, left: itemBounds.left });
        }
      }
      hoverRows = rows.sort((a, b) => a.top - b.top);
      marginBounds = reader.getBoundingClientRect();
    }
    const rows = hoverRows;
    if (!rows.length || !marginBounds || point.x < marginBounds.left || point.x > marginBounds.right
      || point.y < rows[0].top - 8 || point.y > rows.at(-1)!.bottom + 8) return undefined;
    const row = rows[nearestDragBlock(rows, point.y)];
    if (point.x > row.left) return undefined;
    return isMovableArticleBlock(row.node, root) ? row.node : null;
  };
  const hover = (event: PointerEvent) => {
    if (pointer || options.readOnly() || event.pointerType === "touch") return;
    mousePoint = { x: event.clientX, y: event.clientY };
    if (controls.contains(event.target as Node)) { clearLeave(); return; }
    const margin = marginTarget(mousePoint);
    const node = margin === undefined ? selectFrom(event.target as Node) : margin;
    if (node) { clearLeave(); show(node); }
    else if (!host.contains(document.activeElement)) { block = null; refresh(); expand(false); }
  };
  const tap = (event: PointerEvent) => {
    if (event.pointerType !== "mouse" && !pointer && !options.readOnly()) show(selectFrom(event.target as Node));
  };
  const followSelection = () => {
    if (mousePoint && reader.matches(":hover") && marginTarget(mousePoint)) return;
    if (!pointer && !controls.contains(document.activeElement)) show(selectFrom(window.getSelection()?.focusNode ?? null));
  };
  const layoutChanged = () => {
    invalidateLayout();
    refresh();
    if (!pointer && !options.readOnly() && mousePoint && reader.matches(":hover") && !controls.matches(":hover")
      && !controls.contains(document.activeElement)) {
      const node = marginTarget(mousePoint);
      if (node) show(node);
    }
  };
  const leave = () => {
    if (pointer || controls.matches(":hover") || controls.contains(document.activeElement)
      || (mousePoint && reader.matches(":hover") && marginTarget(mousePoint))) return;
    const selected = selectFrom(window.getSelection()?.focusNode ?? null);
    if (selected && host.contains(document.activeElement)) show(selected);
    else { block = null; refresh(); expand(false); }
  };
  const queueLeave = () => {
    clearLeave();
    // Keep the handle reachable while crossing the gap outside the editor's box.
    leaveTimer = window.setTimeout(() => { leaveTimer = 0; leave(); }, 120);
  };
  const releasePointer = () => {
    const held = pointer;
    pointer = null;
    if (held && held.owner.hasPointerCapture(held.id)) held.owner.releasePointerCapture(held.id);
  };
  const lostCapture = () => { if (pointer) cancel(); };
  const focusOut = () => queueMicrotask(() => { if (!frame.contains(document.activeElement)) leave(); });
  function cancel() {
    const started = pointer?.started;
    releasePointer();
    if (started) options.cancel();
    suppressClick = Boolean(started);
    refresh();
  }
  const pointerDown = (event: PointerEvent) => {
    if (options.readOnly() || !block || event.button !== 0) return;
    event.preventDefault();
    clearLeave();
    suppressClick = false;
    wholeList = event.currentTarget === containerHandle;
    const source = activeBlock();
    if (!source) return;
    const owner = activeHandle();
    pointer = { id: event.pointerId, start: { x: event.clientX, y: event.clientY }, started: false, owner, source };
    owner.setPointerCapture(event.pointerId);
  };
  const pointerMove = (event: PointerEvent) => {
    if (!pointer || pointer.id !== event.pointerId || !block) return;
    const point = { x: event.clientX, y: event.clientY };
    if (!pointer.started && Math.hypot(point.x - pointer.start.x, point.y - pointer.start.y) >= 5) {
      pointer.started = options.begin(pointer.source, pointer.start);
      if (!pointer.started) { releasePointer(); return; }
      expand(false);
      boundary.hidden = true;
    }
    if (pointer.started) { event.preventDefault(); options.update(point); }
  };
  const pointerUp = (event: PointerEvent) => {
    if (!pointer || pointer.id !== event.pointerId) return;
    const started = pointer.started;
    releasePointer();
    suppressClick = started;
    if (started) options.finish({ x: event.clientX, y: event.clientY });
    refresh();
  };
  const move = (direction: "before" | "after") => {
    if (options.readOnly() || !block) return;
    const source = activeBlock(), grouped = wholeList;
    const moved = source && options.move(source, direction);
    if (moved) {
      show(moved);
      wholeList = grouped;
      refresh();
      expand(true);
      activeHandle().focus({ preventScroll: true });
    }
  };
  const keydown = (event: KeyboardEvent) => {
    if (event.isComposing) return;
    if (event.key === "Escape") {
      if (pointer) { event.preventDefault(); event.stopPropagation(); cancel(); }
      else if (!directions.hidden && controls.contains(document.activeElement)) { event.preventDefault(); event.stopPropagation(); expand(false); activeHandle().focus(); }
    } else if (controls.contains(event.target as Node) && event.altKey && ["ArrowUp", "ArrowDown"].includes(event.key)) {
      event.preventDefault();
      event.stopPropagation();
      move(event.key === "ArrowUp" ? "before" : "after");
    }
  };
  for (const button of [handle, containerHandle]) {
    button.onclick = () => {
      if (suppressClick) { suppressClick = false; return; }
      wholeList = button === containerHandle;
      refresh();
      button.focus({ preventScroll: true });
      expand(true);
    };
    const activate = () => { if (!pointer) { wholeList = button === containerHandle; refresh(); } };
    button.onpointerenter = activate;
    button.onfocus = activate;
    button.addEventListener("pointerdown", pointerDown);
    button.addEventListener("pointermove", pointerMove);
    button.addEventListener("pointerup", pointerUp);
    button.addEventListener("pointercancel", cancel);
    button.addEventListener("lostpointercapture", lostCapture);
  }
  fold.onclick = () => { if (block) { options.toggleFold(block); refresh(); fold.focus({ preventScroll: true }); } };
  up.onclick = () => move("before");
  down.onclick = () => move("after");
  reader.addEventListener("pointermove", hover, true);
  reader.addEventListener("scroll", layoutChanged, true);
  host.addEventListener("pointerdown", tap, true);
  host.addEventListener("focusin", followSelection);
  reader.addEventListener("pointerleave", queueLeave);
  reader.addEventListener("pointerenter", clearLeave);
  document.addEventListener("keydown", keydown, true);
  frame.addEventListener("focusout", focusOut);
  window.addEventListener("blur", cancel);
  document.addEventListener("selectionchange", followSelection);
  document.fonts.addEventListener("loadingdone", layoutChanged);
  return {
    refresh: () => { invalidateLayout(); refresh(); },
    show,
    destroy() {
      cancel();
      clearLeave();
      for (const button of [handle, containerHandle]) {
        button.removeEventListener("pointerdown", pointerDown);
        button.removeEventListener("pointermove", pointerMove);
        button.removeEventListener("pointerup", pointerUp);
        button.removeEventListener("pointercancel", cancel);
        button.removeEventListener("lostpointercapture", lostCapture);
      }
      reader.removeEventListener("pointermove", hover, true);
      reader.removeEventListener("scroll", layoutChanged, true);
      host.removeEventListener("pointerdown", tap, true);
      host.removeEventListener("focusin", followSelection);
      reader.removeEventListener("pointerleave", queueLeave);
      reader.removeEventListener("pointerenter", clearLeave);
      document.removeEventListener("keydown", keydown, true);
      frame.removeEventListener("focusout", focusOut);
      window.removeEventListener("blur", cancel);
      document.removeEventListener("selectionchange", followSelection);
      document.fonts.removeEventListener("loadingdone", layoutChanged);
      controls.remove();
      boundary.remove();
      markerMeasure.remove();
    }
  };
}
