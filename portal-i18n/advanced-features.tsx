import { useState } from "react"
import { Button } from "@/components/ui/button"
import { advancedFeaturesEnabled, saveAdvancedFeatures } from "@/lib/license-advanced"
import * as keygen from "@/keygen"

export function AdvancedFeaturesToggle() {
  const [enabled] = useState(advancedFeaturesEnabled)
  const [error, setError] = useState(false)
  function toggle() {
    try { saveAdvancedFeatures(!enabled) }
    catch { setError(true); return }
    window.location.reload()
  }
  return <div className="space-y-2">
    <Button type="button" variant="outline" size="sm" aria-pressed={enabled} onClick={toggle}>
      {enabled ? "Disable advanced features" : "Enable advanced features"}
    </Button>
    <p className="text-xs text-content-muted">Show component management and Webhooks. This preference is saved in this browser.</p>
    {error && <p role="alert" className="text-sm">Unable to save this preference. Allow browser storage and try again.</p>}
  </div>
}

export function AdvancedFeaturesPrompt() {
  return <section className="space-y-4 p-6">
    <h1 className="font-owners-wide text-lg">Advanced features</h1>
    <p>Enable advanced features in Settings to view this page.</p>
    <Button asChild variant="outline">
      <a href={`/${encodeURIComponent(keygen.config.id)}/app/general`}>Open settings</a>
    </Button>
  </section>
}
