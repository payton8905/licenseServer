import { readFileSync, writeFileSync } from 'node:fs'

function patch(file, from, to) {
  const source = readFileSync(file, 'utf8').replaceAll('\r\n', '\n')
  if (!source.includes(from)) throw new Error(`Advanced features integration changed: ${file}`)
  writeFileSync(file, source.replace(from, to))
}

writeFileSync('src/lib/license-advanced.ts', readFileSync('/app/license-localization/advanced-features.ts', 'utf8'))
writeFileSync('src/components/license-advanced.tsx', readFileSync('/app/license-localization/advanced-features.tsx', 'utf8'))

const viewsPath = 'src/lib/views.ts'
writeFileSync(viewsPath, 'import { advancedFeaturesEnabled, isAdvancedPath } from "@/lib/license-advanced"\n' + readFileSync(viewsPath, 'utf8') + `
// Changing the preference reloads the portal, so all navigation consumers,
// including its command palette, share the same filtered route catalogue.
if (!advancedFeaturesEnabled()) {
  const webhooksIndex = VIEWS.findIndex(view => view.id === ViewId.Webhooks)
  if (webhooksIndex >= 0) VIEWS.splice(webhooksIndex, 1)
  for (const view of VIEWS) view.routes = view.routes.filter(route => !isAdvancedPath(route.to))
}
`)

const panelPath = 'src/components/sidebar/panel.tsx'
patch(panelPath, ': favorite.accountId === accountId,', ': favorite.accountId === accountId && (advancedFeaturesEnabled() || !isAdvancedPath(favorite.path)),')
writeFileSync(panelPath, 'import { advancedFeaturesEnabled, isAdvancedPath } from "@/lib/license-advanced"\n' + readFileSync(panelPath, 'utf8'))

const checkoutPath = 'src/components/machines/form/check-out.tsx'
patch(checkoutPath, 'options={INCLUDE_OPTIONS}', 'options={INCLUDE_OPTIONS.filter(option => advancedFeaturesEnabled() || option.value !== "components")}')
writeFileSync(checkoutPath, 'import { advancedFeaturesEnabled } from "@/lib/license-advanced"\n' + readFileSync(checkoutPath, 'utf8'))

const machinePath = 'src/pages/app/machine/details.tsx'
const machineSource = readFileSync(machinePath, 'utf8').replaceAll('\r\n', '\n')
const componentField = /<Attribute\.Field\s+variant="text"\s+label="Components"\s+value=\{\s*<GoToButton[\s\S]*?\/>\s*\}\s*\/>/
if (!componentField.test(machineSource)) throw new Error('Machine component link changed')
writeFileSync(machinePath, 'import { advancedFeaturesEnabled } from "@/lib/license-advanced"\n' + machineSource.replace(componentField, '{advancedFeaturesEnabled() && ($&)}'))

for (const page of ['components', 'webhook-endpoints', 'webhook-events']) {
  const pagePath = `src/pages/app/${page}.tsx`
  patch(pagePath, '  const { id } = useParams({ strict: false })', '  const { id } = useParams({ strict: false })\n  if (!advancedFeaturesEnabled()) return <AdvancedFeaturesPrompt />')
  writeFileSync(pagePath, 'import { advancedFeaturesEnabled } from "@/lib/license-advanced"\nimport { AdvancedFeaturesPrompt } from "@/components/license-advanced"\n' + readFileSync(pagePath, 'utf8'))
}

const generalPath = 'src/pages/app/settings/general.tsx'
patch(generalPath, '                <Attribute.Field\n                  label="Theme"', '                <Attribute.Field\n                  label="Advanced features"\n                  variant="none"\n                  value={<AdvancedFeaturesToggle />}\n                />\n                <Attribute.Field\n                  label="Theme"')
writeFileSync(generalPath, 'import { AdvancedFeaturesToggle } from "@/components/license-advanced"\n' + readFileSync(generalPath, 'utf8'))
