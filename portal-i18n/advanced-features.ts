const STORAGE_KEY = "license_portal_advanced_features"

export function advancedFeaturesEnabled(): boolean {
  try { return localStorage.getItem(STORAGE_KEY) === "true" }
  catch { return false }
}

export function saveAdvancedFeatures(enabled: boolean): void {
  localStorage.setItem(STORAGE_KEY, String(enabled))
}

export function isAdvancedPath(path: string): boolean {
  return /\/app\/(?:components|webhook-endpoints|webhook-events)(?:\/|$|\?)/.test(path)
}
