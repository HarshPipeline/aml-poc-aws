/** Title-case UI headings without changing acronyms or mixed-case proper names. */
export function titleCase(value: string): string {
  const minor = new Set(["a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to", "with"]);
  let first = true;
  return value.replace(/[A-Za-z][A-Za-z0-9]*/g, (word, offset: number) => {
    const startsPhrase = first || /[:·—-]\s*$/.test(value.slice(0, offset));
    first = false;
    if (word === word.toUpperCase() || /[A-Z]/.test(word.slice(1))) return word;
    return !startsPhrase && minor.has(word.toLowerCase())
      ? word.toLowerCase()
      : word.charAt(0).toUpperCase() + word.slice(1);
  });
}
