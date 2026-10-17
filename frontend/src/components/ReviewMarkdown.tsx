import { memo, useMemo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { reviewMarkdownPlan } from "../reviewMarkdown";

const MarkdownBlock = memo(function MarkdownBlock({ markdown, definitions, components }: { markdown: string; definitions: string; components: Components }) {
  return <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{definitions ? `${definitions}\n\n${markdown}` : markdown}</ReactMarkdown>;
});

export function ReviewMarkdown({ text, source, components }: { text: string; source: string; components: Components }) {
  const document = source.startsWith(text) ? source : text;
  const plan = useMemo(() => reviewMarkdownPlan(document), [document]);
  return plan.blocks.filter(block => block.start < text.length).map(block =>
    <MarkdownBlock key={block.start} markdown={text.slice(block.start, Math.min(block.end, text.length))} definitions={plan.definitions} components={components} />
  );
}
