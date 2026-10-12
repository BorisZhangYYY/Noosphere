const IMAGE_RE = /!\[[^\]\n]*]\(\s*(?:<([^>\n]+)>|([^\s)\n]+))[^)\n]*\)|<img\b[^>]*\bsrc\s*=\s*["']([^"']+)["'][^>]*>/gi;

type DropSide = "before" | "after";
interface DropBounds { top: number; bottom: number; left: number; width: number }

export function nearestDragBlock(blocks: ReadonlyArray<{ top: number; bottom: number }>, y: number) {
  if (!blocks.length) return -1;
  let low = 0, high = blocks.length;
  while (low < high) {
    const middle = (low + high) >>> 1;
    if (blocks[middle].top <= y) low = middle + 1;
    else high = middle;
  }
  if (!low) return 0;
  const previous = low - 1;
  if (low === blocks.length || y <= blocks[previous].bottom) return previous;
  return y - blocks[previous].bottom <= blocks[low].top - y ? previous : low;
}

export function dragScrollVelocity(y: number, top: number, bottom: number) {
  const edge = Math.min(56, Math.max(1, (bottom - top) / 3));
  if (y < top + edge) return -480 * Math.min(1, (top + edge - y) / edge);
  if (y > bottom - edge) return 480 * Math.min(1, (y - bottom + edge) / edge);
  return 0;
}

export function dragScrollDistance(velocity: number, elapsedMs: number) {
  return velocity * Math.min(50, Math.max(0, elapsedMs)) / 1000;
}

export function insertionWouldMove(sourceIndex: number, insertionIndex: number) {
  return sourceIndex < 0 || (insertionIndex !== sourceIndex && insertionIndex !== sourceIndex + 1);
}

export function dropMarkerBounds(previous: DropBounds | null, next: DropBounds | null, parent: DropBounds) {
  const neighbor = next ?? previous ?? parent;
  return {
    top: previous && next ? (previous.bottom + next.top) / 2 : next?.top ?? previous?.bottom ?? parent.top,
    left: neighbor.left,
    width: neighbor.width,
  };
}

function imageMoveElement(image: HTMLImageElement): HTMLElement {
  let source: HTMLElement = image.closest<HTMLElement>("[data-type='img']") ?? image;
  if (source.parentElement?.tagName === "A" && !source.parentElement.textContent?.trim()) source = source.parentElement;
  const paragraph = source.closest<HTMLParagraphElement>("p");
  if (paragraph && !paragraph.textContent?.trim() && paragraph.querySelectorAll("img").length === 1) source = paragraph;
  return source;
}

export function createImageDropResolver(root: HTMLElement, imageIndex: number,
  boundsFor: (node: Node) => DropBounds = node => {
    if (node instanceof Element) return node.getBoundingClientRect();
    const range = document.createRange();
    range.selectNode(node);
    return range.getBoundingClientRect();
  }) {
  const image = root.querySelectorAll<HTMLImageElement>("img")[imageIndex];
  const source = image ? imageMoveElement(image) : null;
  const parentCache = new WeakMap<HTMLElement, { siblings: Node[]; indexes: Map<Node, number> }>();
  return (target: HTMLElement, side: DropSide) => {
    if (!source || !root.contains(source) || target === root || !root.contains(target)
        || (target.tagName === "H1" && side === "before")) return null;
    const parent = target.tagName === "LI" ? target : target.parentElement;
    if (!parent || !root.contains(parent) || source === target || source.contains(parent)) return null;
    let cached = parentCache.get(parent);
    if (!cached) {
      const siblings = Array.from(parent.childNodes).filter(node => node.nodeType !== Node.TEXT_NODE
        || !/^[\s\u200B\uFEFF]*$/.test(node.textContent ?? ""));
      cached = { siblings, indexes: new Map(siblings.map((node, index) => [node, index])) };
      parentCache.set(parent, cached);
    }
    const { siblings, indexes } = cached;
    if (target.tagName !== "LI" && !indexes.has(target)) return null;
    const insertionIndex = target.tagName === "LI" ? (side === "before" ? 0 : siblings.length)
      : (indexes.get(target) ?? -1) + Number(side === "after");
    if (!insertionWouldMove(indexes.get(source) ?? -1, insertionIndex)) return null;

    const visibleBounds = (index: number, direction: number): DropBounds | null => {
      for (; index >= 0 && index < siblings.length; index += direction) {
        const bounds = boundsFor(siblings[index]);
        if (bounds.width || bounds.bottom !== bounds.top) return bounds;
      }
      return null;
    };
    const previous = visibleBounds(insertionIndex - 1, -1), next = visibleBounds(insertionIndex, 1);
    const parentBounds = parent.tagName === "LI" ? boundsFor(parent) : previous ?? next ?? boundsFor(parent);
    const marker = dropMarkerBounds(previous, next, parentBounds);
    if (parent.tagName === "LI") { marker.left = parentBounds.left; marker.width = parentBounds.width; }
    return { target, side, marker };
  };
}

export function resolveImageDropPosition(root: HTMLElement, imageIndex: number, target: HTMLElement, side: DropSide) {
  return createImageDropResolver(root, imageIndex)(target, side);
}

export function imageName(source: string) {
  const clean = source.split(/[?#]/, 1)[0];
  try { return decodeURIComponent(clean.split("/").pop() ?? ""); }
  catch { return clean.split("/").pop() ?? ""; }
}

export function preserveDraggedImageReferences(candidate: string, original: string): string | null {
  const references = new Map<string, string[]>();
  for (const match of original.matchAll(IMAGE_RE)) {
    const name = imageName(match[1] || match[2] || match[3] || "");
    references.set(name, [...(references.get(name) ?? []), match[0]]);
  }
  let valid = true;
  const restored = candidate.replace(IMAGE_RE, (reference, angle, target, html) => {
    const queue = references.get(imageName(angle || target || html || ""));
    if (!queue?.length) { valid = false; return reference; }
    const caption = reference.match(/^!\[([^\]\n]*)]/)?.[1];
    const matchingCaption = queue.findIndex(item => item.match(/^!\[([^\]\n]*)]/)?.[1] === caption);
    return queue.splice(Math.max(0, matchingCaption), 1)[0];
  });
  return valid && [...references.values()].every(queue => queue.length === 0) ? restored : null;
}

export function imageDropMarkdown(
  root: HTMLElement, imageIndex: number, target: HTMLElement, side: DropSide,
  serialize: (html: string) => string, original: string,
): string | null {
  if (!resolveImageDropPosition(root, imageIndex, target, side)) return null;
  const elements = Array.from(root.querySelectorAll<HTMLElement>("*"));
  const targetIndex = elements.indexOf(target);
  if (targetIndex < 0) return null;
  const clone = root.cloneNode(true) as HTMLElement;
  const destination = clone.querySelectorAll<HTMLElement>("*")[targetIndex];
  const image = clone.querySelectorAll<HTMLImageElement>("img")[imageIndex];
  if (!image || !destination) return null;
  const source = imageMoveElement(image);
  const moving = source.tagName === "P" ? source : Object.assign(document.createElement("p"), { innerHTML: source.outerHTML });
  if (moving !== source) source.remove();
  if (destination.tagName === "LI") {
    // Keep the image inside its point, rather than introducing a sibling of <li>.
    const inline = Array.from(destination.childNodes).filter(node => !(node instanceof HTMLElement)
      || !["P", "UL", "OL", "BLOCKQUOTE", "PRE", "TABLE"].includes(node.tagName));
    if (inline.some(node => node.textContent?.trim())) {
      const paragraph = document.createElement("p");
      destination.insertBefore(paragraph, inline[0]);
      inline.forEach(node => paragraph.append(node));
    }
    if (side === "before") destination.prepend(moving);
    else destination.append(moving);
  } else destination.insertAdjacentElement(side === "before" ? "beforebegin" : "afterend", moving);
  if (clone.textContent !== root.textContent) return null;
  return preserveDraggedImageReferences(serialize(clone.innerHTML), original);
}
