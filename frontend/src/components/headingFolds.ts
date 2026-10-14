interface FoldOptions {
  root: () => HTMLElement | null;
  readOnly: () => boolean;
  serialize: (html: string) => string;
}

interface HeadingRow {
  node: HTMLElement;
  index: number;
  level: number;
  signature: string;
  context: string;
  folded: boolean;
}

export function headingLevel(node: Element) {
  return /^H[1-6]$/.test(node.tagName) ? Number(node.tagName[1]) : 0;
}

export function createHeadingFolds(options: FoldOptions) {
  let rows: HeadingRow[] = [];
  const sectionNodes = (heading: HTMLElement) => {
    const nodes = [heading], level = headingLevel(heading);
    if (!level) return nodes;
    let next = heading.nextElementSibling;
    while (next instanceof HTMLElement && !["footnotes-block", "link-ref-defs-block"].includes(next.dataset.type ?? "")
      && !(headingLevel(next) && headingLevel(next) <= level)) {
      nodes.push(next);
      next = next.nextElementSibling;
    }
    return nodes;
  };
  const apply = () => {
    const root = options.root();
    if (!root) return;
    const hidden = new Set<HTMLElement>();
    if (!options.readOnly()) rows.filter(row => row.folded).forEach(row => sectionNodes(row.node).slice(1).forEach(node => hidden.add(node)));
    Array.from(root.children).forEach(node => {
      if (node instanceof HTMLElement) node.classList.toggle("noosphere-fold-hidden", hidden.has(node));
    });
    rows.forEach(row => row.node.classList.toggle("noosphere-heading-folded", row.folded && !options.readOnly()));
  };
  const refresh = () => {
    const root = options.root();
    if (!root) { rows = []; return; }
    const previous = rows, used = new Set<HeadingRow>();
    const next = Array.from(root.children).flatMap((node, index) => node instanceof HTMLElement && headingLevel(node)
      ? [{ node, index, level: headingLevel(node), signature: options.serialize(node.outerHTML).trim(), context: options.serialize(sectionNodes(node)[1]?.outerHTML ?? "").trim(), folded: false }] : []);
    const signatures = new Set(next.map(row => row.signature));
    rows = next.map(row => {
      let old = previous.find(candidate => !used.has(candidate) && candidate.node === row.node)
        // Native history replaces nodes before its delayed Markdown callback; context disambiguates equal headings.
        ?? previous.find(candidate => !used.has(candidate) && candidate.signature === row.signature && candidate.context === row.context)
        ?? previous.find(candidate => !used.has(candidate) && candidate.signature === row.signature);
      // An edited heading keeps its view state without assigning persistent IDs to Markdown.
      if (!old && !previous.some(candidate => candidate.signature === row.signature)) old = previous.find(candidate =>
        !used.has(candidate) && candidate.index === row.index && candidate.level === row.level && !signatures.has(candidate.signature));
      if (old) { used.add(old); row.folded = old.folded; }
      return row;
    });
    apply();
  };
  const isFolded = (node: HTMLElement) => rows.some(row => row.node === node && row.folded);
  const capture = (mapping: Map<HTMLElement, number[]>) => rows.flatMap(row => {
    const path = mapping.get(row.node);
    return row.folded && path?.length === 1 ? [path[0]] : [];
  });
  const restore = (indices: number[], mapping: Map<HTMLElement, number[]>) => {
    refresh();
    const folded = new Set(indices);
    rows.forEach(row => { const path = mapping.get(row.node); row.folded = Boolean(path?.length === 1 && folded.has(path[0])); });
    apply();
  };
  const reveal = (node: Element) => {
    refresh();
    rows.forEach(row => {
      if (row.folded && sectionNodes(row.node).slice(1).some(child => child === node || child.contains(node))) row.folded = false;
    });
    apply();
  };
  return {
    refresh, isFolded, capture, restore, reveal, sectionNodes,
    canFold: (node: HTMLElement) => Boolean(headingLevel(node) && sectionNodes(node).length > 1),
    toggle(node: HTMLElement) {
      refresh();
      const row = rows.find(candidate => candidate.node === node);
      if (!row || sectionNodes(node).length === 1 || options.readOnly()) return false;
      row.folded = !row.folded;
      if (row.folded) {
        const selection = window.getSelection();
        if (selection?.focusNode && sectionNodes(node).slice(1).some(child => child.contains(selection.focusNode))) {
          const range = document.createRange();
          range.selectNodeContents(node);
          range.collapse(false);
          selection.removeAllRanges();
          selection.addRange(range);
        }
      }
      apply();
      return true;
    },
    destroy() {
      const root = options.root();
      root?.querySelectorAll(".noosphere-fold-hidden, .noosphere-heading-folded").forEach(node => node.classList.remove("noosphere-fold-hidden", "noosphere-heading-folded"));
      rows = [];
    }
  };
}
