import { fromMarkdown } from "mdast-util-from-markdown";
import { gfmFromMarkdown } from "mdast-util-gfm";
import { gfm } from "micromark-extension-gfm";

export interface MarkdownBlock {
  type: string;
  start: number;
  end: number;
  raw: string;
  depth?: number;
}

const MOVABLE_TYPES = new Set(["paragraph", "list", "blockquote", "table", "code", "thematicBreak", "heading"]);

export function isMovableMarkdownBlock(block: MarkdownBlock) {
  return MOVABLE_TYPES.has(block.type);
}

export function markdownStateKey(markdown: string) {
  return markdown.replace(/(?:\r?\n)+$/, "");
}

export function markdownBlocks(markdown: string): MarkdownBlock[] {
  return fromMarkdown(markdown, { extensions: [gfm()], mdastExtensions: [gfmFromMarkdown()] }).children.flatMap(node => {
    const start = node.position?.start.offset, end = node.position?.end.offset;
    return start === undefined || end === undefined ? [] : [{ type: node.type, start, end, raw: markdown.slice(start, end),
      ...(node.type === "heading" ? { depth: node.depth } : {}) }];
  });
}

interface MarkdownNode {
  type: string;
  position?: { start: { offset?: number; column: number }; end: { offset?: number } };
  children?: MarkdownNode[];
  ordered?: boolean | null;
  start?: number | null;
}

const markdownTree = (markdown: string) => fromMarkdown(markdown, { extensions: [gfm()], mdastExtensions: [gfmFromMarkdown()] });
const nodeAtPath = (tree: MarkdownNode, path: number[]) => path.reduce<MarkdownNode | undefined>((node, index) => node?.children?.[index], tree);

export function moveListItemMarkdown(markdown: string, sourcePath: number[], targetPath: number[], side: "before" | "after") {
  if (sourcePath.length < 2 || sourcePath.length !== targetPath.length
    || sourcePath.slice(0, -1).some((index, depth) => index !== targetPath[depth])) return null;
  const tree = markdownTree(markdown), list = nodeAtPath(tree, sourcePath.slice(0, -1));
  if (list?.type !== "list" || !list.children?.every(item => item.type === "listItem")) return null;
  const items = list.children, source = sourcePath.at(-1)!, target = targetPath.at(-1)!;
  const insertion = target + Number(side === "after");
  if (!items[source] || !items[target] || insertion === source || insertion === source + 1) return null;
  const start = list.position?.start.offset, end = list.position?.end.offset;
  if (start === undefined || end === undefined) return null;
  const ranges = items.map(item => ({ start: item.position?.start.offset, end: item.position?.end.offset }));
  if (ranges.some(range => range.start === undefined || range.end === undefined)) return null;
  const raw = ranges.map(range => markdown.slice(range.start!, range.end!));
  const gaps = ranges.slice(0, -1).map((range, index) => markdown.slice(range.end!, ranges[index + 1].start!));
  if (gaps.some(gap => !/^\s*$/.test(gap))) return null;
  const order = items.map((_, index) => index);
  order.splice(source, 1);
  order.splice(insertion - Number(source < insertion), 0, source);
  const reordered = order.map((index, destination) => {
    const item = raw[index];
    if (!list.ordered) return item;
    const marker = item.match(/^(\d+)([.)])([ \t]+)/);
    if (!marker) return null;
    const number = String((list.start ?? 1) + destination), delta = number.length - marker[1].length;
    const indent = (list.position?.start.column ?? 1) - 1 + marker[0].length;
    // A wider ordered marker must carry its continuation lines to preserve nested blocks.
    const lines = item.slice(marker[1].length).split(/\r?\n/);
    if (delta) for (let line = 1; line < lines.length; line++) {
      const whitespace = lines[line].match(/^[ \t]*/)?.[0] ?? "";
      if (whitespace.includes("\t")) return null;
      if (whitespace.length >= indent) lines[line] = delta > 0 ? " ".repeat(delta) + lines[line] : lines[line].slice(-delta);
    }
    return number + lines.join(markdown.includes("\r\n") ? "\r\n" : "\n");
  });
  if (reordered.some(item => item === null)) return null;
  const replacement = reordered.map((item, index) => item + (gaps[index] ?? "")).join("");
  const next = markdown.slice(0, start) + replacement + markdown.slice(end);
  const semanticKey = (node: MarkdownNode) => JSON.stringify(node, (key, value) => ["position", "spread"].includes(key) ? undefined : value);
  const expected = structuredClone(tree), expectedList = nodeAtPath(expected, sourcePath.slice(0, -1))!;
  expectedList.children = order.map(index => items[index]);
  return semanticKey(markdownTree(next)) === semanticKey(expected) ? next : null;
}

export function reconcileBlockEdits(original: string, rendered: string, edited: string) {
  if (markdownStateKey(rendered) === markdownStateKey(edited)) return original;
  const source = markdownBlocks(original), baseline = markdownBlocks(rendered), changed = markdownBlocks(edited);
  if (source.length !== baseline.length || baseline.length !== changed.length) return edited;
  let next = original;
  const replacements: Array<{ block: MarkdownBlock; raw: string }> = [];
  for (let index = 0; index < source.length; index++) {
    if (source[index].type !== baseline[index].type || baseline[index].type !== changed[index].type) return edited;
    if (baseline[index].raw === changed[index].raw) continue;
    // Renumbered footnote references need the complete canonical document to remain coherent.
    if (!isMovableMarkdownBlock(source[index]) || /\[\^[^\]]+\]/.test(changed[index].raw)) return edited;
    replacements.push({ block: source[index], raw: changed[index].raw });
  }
  for (const { block, raw } of replacements.reverse()) next = next.slice(0, block.start) + raw + next.slice(block.end);
  return next;
}

export function moveArticleBlockMarkdown(markdown: string, sourceIndex: number, targetIndex: number, side: "before" | "after") {
  return moveArticleRangeMarkdown(markdown, sourceIndex, sourceIndex + 1, targetIndex, side);
}

export function headingSectionEnd(blocks: MarkdownBlock[], index: number) {
  const heading = blocks[index];
  if (heading?.type !== "heading") return index + 1;
  let end = index + 1;
  while (end < blocks.length && !(blocks[end].type === "heading" && blocks[end].depth! <= heading.depth!)) end++;
  while (end > index + 1 && ["definition", "footnoteDefinition"].includes(blocks[end - 1].type)) end--;
  return end;
}

export function articleBlockMovePlan(blocks: MarkdownBlock[], source: number, target: number, side: "before" | "after", folded: Set<number>) {
  const grouped = blocks[source]?.type === "heading" && folded.has(source);
  const end = grouped ? headingSectionEnd(blocks, source) : source + 1;
  let owner = target;
  if (grouped) {
    while (owner >= 0 && !(blocks[owner]?.type === "heading" && blocks[owner].depth! <= blocks[source].depth!)) owner--;
  } else {
    const container = [...folded].sort((a, b) => a - b).find(index => index <= target && target < headingSectionEnd(blocks, index));
    if (container !== undefined) owner = container;
  }
  if (owner >= 0 && (grouped || folded.has(owner))) {
    // The assembled title anchors the article; its introductory prose is not a movable chapter.
    const anchoredTitle = owner === 0 && blocks[owner].type === "heading" && blocks[owner].depth === 1;
    const nextHeading = anchoredTitle ? blocks.findIndex((block, index) => index > 0 && block.type === "heading") : -1;
    target = side === "before" ? owner : anchoredTitle && nextHeading > 0 ? nextHeading - 1 : headingSectionEnd(blocks, owner) - 1;
  }
  return { source, end, target, side, insertion: target + Number(side === "after") };
}

export function moveArticleRangeMarkdown(markdown: string, sourceIndex: number, sourceEnd: number, targetIndex: number, side: "before" | "after") {
  const blocks = markdownBlocks(markdown);
  const source = blocks[sourceIndex], target = blocks[targetIndex];
  const insertion = targetIndex + Number(side === "after");
  const count = sourceEnd - sourceIndex, last = blocks[sourceEnd - 1];
  if (!source || !target || !last || count < 1 || !isMovableMarkdownBlock(source)
    || (count > 1 && source.type !== "heading") || (insertion >= sourceIndex && insertion <= sourceEnd)
    || (sourceIndex === 0 && source.type === "heading" && source.depth === 1)
    || (targetIndex === 0 && target.type === "heading" && target.depth === 1 && side === "before")) return null;
  const cutEnd = blocks[sourceEnd]?.start ?? markdown.length;
  if (!/^\s*$/.test(markdown.slice(last.end, cutEnd))) return null;
  const at = side === "before" ? target.start : target.end;
  const remaining = markdown.slice(0, source.start) + markdown.slice(cutEnd);
  const offset = at > source.start ? at - (cutEnd - source.start) : at;
  const prefix = remaining.slice(0, offset), suffix = remaining.slice(offset);
  const newline = markdown.includes("\r\n") ? "\r\n" : "\n";
  const separator = newline + newline;
  const before = prefix && !/(?:\r?\n){2}$/.test(prefix) ? separator : "";
  const after = suffix && !/^(?:\r?\n){2}/.test(suffix) ? separator : "";
  const next = prefix + before + markdown.slice(source.start, last.end) + after + suffix;
  const expected = blocks.filter((_, index) => index < sourceIndex || index >= sourceEnd);
  const destination = insertion - (sourceEnd <= insertion ? count : 0);
  expected.splice(destination, 0, ...blocks.slice(sourceIndex, sourceEnd));
  const parsed = markdownBlocks(next);
  // A moved chapter must not absorb unrelated content at its new location.
  if (count > 1 && headingSectionEnd(parsed, destination) !== destination + count) return null;
  return parsed.length === expected.length && parsed.every((block, index) =>
    block.type === expected[index].type && block.raw === expected[index].raw) ? next : null;
}

export function moveMappedBlockMarkdown(markdown: string, sourcePath: number[], targetPath: number[], side: "before" | "after", sourceEnd = sourcePath[0] + 1) {
  return sourcePath.length === 1 && targetPath.length === 1
    ? moveArticleRangeMarkdown(markdown, sourcePath[0], sourceEnd, targetPath[0], side)
    : moveListItemMarkdown(markdown, sourcePath, targetPath, side);
}

export function articleBlockMap(root: HTMLElement, markdown: string, serialize: (html: string) => string, render: (markdown: string) => string) {
  const blocks = markdownBlocks(markdown);
  const tree = markdownTree(markdown);
  const definitions = blocks.filter(block => ["definition", "footnoteDefinition"].includes(block.type)).map(block => block.raw).join("\n\n");
  const signatures = new Map<string, number[]>();
  const remember = (node: Element, index: number) => {
    const signature = serialize(node.outerHTML).trim();
    signatures.set(signature, [...(signatures.get(signature) ?? []), index]);
  };
  const template = document.createElement("div");
  template.innerHTML = render(markdown);
  const visibleNodes = Array.from(template.children).filter(node => !["footnotes-block", "link-ref-defs-block"].includes(node.getAttribute("data-type") ?? ""));
  const visibleBlocks = blocks.map((block, index) => ({ block, index })).filter(({ block }) => !["definition", "footnoteDefinition"].includes(block.type));
  if (visibleNodes.length === visibleBlocks.length) visibleNodes.forEach((node, index) => remember(node, visibleBlocks[index].index));
  else visibleBlocks.forEach(({ block, index }) => {
    template.innerHTML = render(block.raw + (definitions ? "\n\n" + definitions : ""));
    const nodes = Array.from(template.children).filter(node => !["footnotes-block", "link-ref-defs-block"].includes(node.getAttribute("data-type") ?? ""));
    if (nodes.length === 1) remember(nodes[0], index);
  });
  const mapping = new Map<HTMLElement, number[]>();
  const mapList = (element: HTMLElement, list: MarkdownNode, path: number[]) => {
    const items = Array.from(element.children).filter((node): node is HTMLElement => node instanceof HTMLElement && node.tagName === "LI");
    if (list.type !== "list" || items.length !== list.children?.length) return;
    items.forEach((item, index) => {
      const itemPath = [...path, index], node = list.children![index];
      mapping.set(item, itemPath);
      const childLists = node.children?.flatMap((child, childIndex) => child.type === "list" ? [{ child, childIndex }] : []) ?? [];
      const elements = Array.from(item.children).filter((child): child is HTMLElement => child instanceof HTMLElement && ["UL", "OL"].includes(child.tagName));
      if (elements.length === childLists.length) childLists.forEach(({ child, childIndex }, nested) => mapList(elements[nested], child, [...itemPath, childIndex]));
    });
  };
  Array.from(root.children).forEach(node => {
    if (!(node instanceof HTMLElement)) return;
    const index = signatures.get(serialize(node.outerHTML).trim())?.shift();
    if (index !== undefined) {
      mapping.set(node, [index]);
      if (["UL", "OL"].includes(node.tagName)) mapList(node, tree.children[index], [index]);
    }
  });
  return { blocks, mapping };
}

export function isMovableArticleBlock(node: Element | null, root: HTMLElement): node is HTMLElement {
  if (!(node instanceof HTMLElement)) return false;
  if (node.tagName === "LI") return Boolean(outerArticleList(node, root));
  if (node.parentElement !== root) return false;
  if (/^H[1-6]$/.test(node.tagName)) return node.tagName !== "H1" || node !== root.firstElementChild;
  if (node.tagName === "P") return Boolean(node.textContent?.replace(/[\s\u200B\uFEFF]/g, ""));
  return ["UL", "OL", "BLOCKQUOTE", "TABLE", "PRE", "HR"].includes(node.tagName)
    || (node.tagName === "DIV" && node.dataset.type === "code-block");
}

export function outerArticleList(node: Element, root: HTMLElement): HTMLElement | null {
  let parent: Element | null = node;
  while (parent && parent.parentElement !== root) parent = parent.parentElement;
  return parent instanceof HTMLElement && ["UL", "OL"].includes(parent.tagName) ? parent : null;
}

export function articleNodePath(root: HTMLElement, node: Node) {
  const path: number[] = [];
  if (!(node instanceof HTMLElement)) return null;
  let current: HTMLElement = node;
  while (current.parentElement && current.parentElement !== root) {
    path.unshift(Array.from(current.parentElement.children).filter(child => child.tagName !== "WBR").indexOf(current));
    current = current.parentElement;
  }
  const index = Array.from(root.children).indexOf(current as Element);
  return index < 0 ? null : [index, ...path];
}

export function articleNodeAtPath(root: HTMLElement, path: number[]) {
  let node: Element | undefined = root.children[path[0]];
  for (const index of path.slice(1)) node = node && Array.from(node.children).filter(child => child.tagName !== "WBR")[index];
  return node instanceof HTMLElement ? node : null;
}

export function createBlockDropResolver(root: HTMLElement, source: HTMLElement,
  boundsFor: (node: HTMLElement) => { top: number; bottom: number; left: number; width: number }, lastSource = source) {
  const siblings = Array.from(root.children).filter((node): node is HTMLElement => node instanceof HTMLElement);
  const sourceIndex = siblings.indexOf(source);
  const sourceEnd = siblings.indexOf(lastSource) + 1;
  return (target: HTMLElement, side: "before" | "after") => {
    const index = siblings.indexOf(target), insertion = index + Number(side === "after");
    if (sourceIndex < 0 || index < 0 || !root.contains(source) || source.parentElement !== root
      || target.parentElement !== root || (insertion >= sourceIndex && insertion <= sourceEnd)
      || (index === 0 && target.tagName === "H1" && side === "before")
      || ["footnotes-block", "link-ref-defs-block"].includes(target.dataset.type ?? "")) return null;
    const visibleBounds = (start: number, direction: number) => {
      for (let at = start; at >= 0 && at < siblings.length; at += direction) {
        const bounds = boundsFor(siblings[at]);
        if (bounds.width || bounds.bottom !== bounds.top) return bounds;
      }
      return null;
    };
    const previous = visibleBounds(insertion - 1, -1), next = visibleBounds(insertion, 1);
    const neighbor = next ?? previous ?? boundsFor(root);
    return { target, side, marker: { top: previous && next ? (previous.bottom + next.top) / 2 : next?.top ?? previous?.bottom ?? neighbor.top,
      left: neighbor.left, width: neighbor.width } };
  };
}

export function remapMovedBlock(index: number, source: number, insertion: number) {
  return remapMovedRange(index, source, source + 1, insertion);
}

export function remapMovedRange(index: number, source: number, end: number, insertion: number) {
  const count = end - source, destination = insertion - (end <= insertion ? count : 0);
  if (index >= source && index < end) return destination + index - source;
  const remaining = index - (index >= end ? count : 0);
  return remaining + (remaining >= destination ? count : 0);
}

export function captureBlockSelection(root: HTMLElement, mapping: Map<HTMLElement, number[]>) {
  const selection = window.getSelection();
  const point = (node: Node | null, offset: number) => {
    if (!node || !root.contains(node)) return null;
    let block = node instanceof HTMLElement ? node : node.parentElement;
    while (block && block !== root && !mapping.has(block)) block = block.parentElement;
    const path = block && mapping.get(block);
    if (!block || !path) return null;
    const range = document.createRange();
    range.selectNodeContents(block);
    range.setEnd(node, offset);
    return { path, textOffset: range.toString().length, forward: offset === 0 };
  };
  const anchor = point(selection?.anchorNode ?? null, selection?.anchorOffset ?? 0);
  const focus = point(selection?.focusNode ?? null, selection?.focusOffset ?? 0);
  return anchor && focus ? { anchor, focus } : null;
}

export function restoreBlockSelection(snapshot: ReturnType<typeof captureBlockSelection>, sourcePath: number[], insertion: number, mapping: Map<HTMLElement, number[]>, count = 1) {
  if (!snapshot) return;
  const parentPath = sourcePath.slice(0, -1), source = sourcePath.at(-1)!;
  const point = (saved: NonNullable<typeof snapshot>["anchor"]) => {
    const path = [...saved.path];
    if (path.length > parentPath.length && parentPath.every((index, depth) => index === path[depth])) {
      path[parentPath.length] = remapMovedRange(path[parentPath.length], source, source + count, insertion);
    }
    const block = Array.from(mapping).find(([, address]) => address.length === path.length && address.every((index, depth) => index === path[depth]))?.[0];
    if (!block) return null;
    // Text offsets survive Vditor's temporary caret markers and inline-node normalization.
    const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    let node: Node | null, last: Node | null = null, remaining = saved.textOffset;
    while ((node = walker.nextNode())) {
      const length = node.textContent?.length ?? 0;
      if (remaining < length || (remaining === length && !saved.forward)) return { node, offset: remaining };
      remaining -= length;
      last = node;
    }
    return { node: last ?? block, offset: last?.textContent?.length ?? 0 };
  };
  const anchor = point(snapshot.anchor), focus = point(snapshot.focus);
  if (anchor && focus) window.getSelection()?.setBaseAndExtent(anchor.node, anchor.offset, focus.node, focus.offset);
}
