const STORAGE_KEY = "license_portal_advanced_features"

export function advancedFeaturesEnabled(): boolean {
  try { return localStorage.getItem(STORAGE_KEY) === "true" }
  catch { return false }
}

export function saveAdvancedFeatures(enabled: boolean): void {
  localStorage.setItem(STORAGE_KEY, String(enabled))
}

export function isAdvancedPath(path: string): boolean {
  return /\/app\/(?:groups|components|processes|packages|releases|artifacts|platforms|arches|channels|engines|webhook-endpoints|webhook-events|tokens|event-logs|request-logs|team|permissions|developers|billing|learn)(?:\/|$|\?|#)/.test(path)
}

export function isAdvancedResource(resource: string): boolean {
  return isAdvancedPath(`/app/${resource}`)
}
