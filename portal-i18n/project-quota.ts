export function projectQuotaMetadata(metadata: Record<string, unknown> | null | undefined, fallback?: Record<string, unknown> | null): Record<string, unknown> {
  const source = metadata ?? {}
  const has = (key: string) => Object.prototype.hasOwnProperty.call(source, key)
  if (has("max_projects") && has("maxProjects") && source.max_projects !== source.maxProjects) {
    throw new Error("Project quota contains conflicting values.")
  }
  const inherited = fallback ?? {}
  if (!has("max_projects") && !has("maxProjects") && Object.prototype.hasOwnProperty.call(inherited, "max_projects") && Object.prototype.hasOwnProperty.call(inherited, "maxProjects") && inherited.max_projects !== inherited.maxProjects) {
    throw new Error("Project quota contains conflicting values.")
  }
  const value = has("max_projects") ? source.max_projects : has("maxProjects") ? source.maxProjects : inherited.max_projects ?? inherited.maxProjects
  if (typeof value !== "number" || !Number.isInteger(value) || (value !== -1 && (value < 1 || value > 2147483647))) {
    throw new Error("Project quota is required. Enter a positive integer or select unlimited.")
  }
  const { maxProjects: _camel, ...rest } = source
  void _camel
  return { ...rest, max_projects: value }
}
