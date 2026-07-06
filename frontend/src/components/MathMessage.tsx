import { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import rehypeSanitize, {
  defaultSchema,
  type Options as RehypeSanitizeOptions,
} from 'rehype-sanitize';
import remarkMath from 'remark-math';
import 'katex/dist/katex.min.css';
import { normalizeMathDelimiters } from '../utils/mathContent';

interface MathMessageProps {
  content: string;
  isUser?: boolean;
}

const katexSanitizeSchemaWithKatex: RehypeSanitizeOptions = {
  ...defaultSchema,
  tagNames: [
    ...(defaultSchema.tagNames ?? []),
    'annotation',
    'math',
    'mfrac',
    'mi',
    'mn',
    'mo',
    'mover',
    'mpadded',
    'mphantom',
    'mroot',
    'mrow',
    'mspace',
    'msqrt',
    'mstyle',
    'msub',
    'msubsup',
    'msup',
    'mtable',
    'mtd',
    'mtext',
    'mtr',
    'semantics',
  ],
  attributes: {
    ...defaultSchema.attributes,
    '*': [...(defaultSchema.attributes?.['*'] ?? []), 'aria-hidden'],
    annotation: [...(defaultSchema.attributes?.annotation ?? []), 'encoding'],
    code: [
      ...(defaultSchema.attributes?.code ?? []),
      ['className', /^language-./, 'math-inline', 'math-display'],
    ],
    div: [...(defaultSchema.attributes?.div ?? []), ['className', 'math', 'math-display']],
    math: [...(defaultSchema.attributes?.math ?? []), 'xmlns', 'display'],
    span: [
      ...(defaultSchema.attributes?.span ?? []),
      ['className', /^katex/, /^base$/, /^strut$/, /^m[a-z]+$/, /^pstrut$/, /^sizing$/, /^reset-/],
    ],
  },
};

export function MathMessage({ content, isUser = false }: MathMessageProps) {
  const normalizedContent = useMemo(() => normalizeMathDelimiters(content), [content]);

  return (
    <div className={isUser ? 'math-message math-message-user' : 'math-message math-message-tutor'}>
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[rehypeKatex, [rehypeSanitize, katexSanitizeSchemaWithKatex]]}
        components={{
          a: ({ node, ...props }) => {
            void node;
            return <a {...props} target="_blank" rel="noopener noreferrer" />;
          },
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
}
