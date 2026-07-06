export function normalizeMathDelimiters(content: string): string {
  return content
    .replace(
      /\$\$([^\n$][\s\S]*?[^\n$]?)\$\$/g,
      (_match, formula: string) => `$$\n${formula.trim()}\n$$`,
    )
    .replace(/\\\[((?:.|\n)*?)\\\]/g, (_match, formula: string) => `\n$$\n${formula.trim()}\n$$`)
    .replace(/\\\(((?:.|\n)*?)\\\)/g, (_match, formula: string) => `$${formula.trim()}$`);
}
