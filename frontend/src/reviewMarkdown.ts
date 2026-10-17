import { fromMarkdown } from "mdast-util-from-markdown";
import { gfmFromMarkdown } from "mdast-util-gfm";
import { gfm } from "micromark-extension-gfm";

export function reviewMarkdownPlan(source: string) {
  const nodes = fromMarkdown(source, { extensions: [gfm()], mdastExtensions: [gfmFromMarkdown()] }).children;
  // Footnote numbering and back-links require a single document scope.
  if (nodes.some(node => node.type === "footnoteDefinition")) {
    return { blocks: [{ start: 0, end: source.length }], definitions: "" };
  }
  const starts = nodes.map((node, index) => index === 0 ? 0 : source.lastIndexOf("\n", (node.position?.start.offset ?? 0) - 1) + 1);
  return {
    blocks: starts.map((start, index) => ({ start, end: starts[index + 1] ?? source.length })),
    definitions: nodes.filter(node => node.type === "definition")
      .map(node => source.slice(node.position!.start.offset!, node.position!.end.offset!)).join("\n\n")
  };
}
