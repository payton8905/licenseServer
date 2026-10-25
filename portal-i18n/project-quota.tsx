import { useId } from "react"
import { useFormContext, useWatch } from "react-hook-form"
import { Input } from "@/components/ui/input"
import type { MetadataPair } from "@/schemas/metadata"

export function ProjectQuotaField() {
  const id = useId()
  const form = useFormContext<{ metadata: MetadataPair[] }>()
  const rows = useWatch({ control: form.control, name: "metadata" }) ?? []
  const quota = rows.find(row => row.key === "max_projects" || row.key === "maxProjects")
  const unlimited = quota?.value === "-1"
  function update(value: string) {
    const rest = rows.filter(row => row.key !== "max_projects" && row.key !== "maxProjects")
    form.setValue("metadata", [...rest, { id: "project-quota", key: "max_projects", type: "integer", value }], { shouldDirty: true, shouldValidate: true })
  }
  return <div className="mb-5 space-y-3 rounded border border-accent p-4">
    <label htmlFor={id} className="block text-sm font-medium">Project quota per deployment</label>
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={unlimited} onChange={event => update(event.target.checked ? "-1" : "")} />
      Unlimited projects
    </label>
    <Input id={id} type="number" min={1} max={2147483647} step={1} disabled={unlimited} value={unlimited ? "" : quota?.value ?? ""} onChange={event => update(event.target.value)} placeholder="Enter project limit..." />
    <p className="text-xs text-content-muted">Set a positive integer or select unlimited. A license without its own quota uses the policy default when issued. Changing a policy does not change previously issued license quotas.</p>
  </div>
}
