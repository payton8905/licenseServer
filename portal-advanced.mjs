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
  for (let i = VIEWS.length - 1; i >= 0; i--) {
    if ([ViewId.Distribution, ViewId.Webhooks, ViewId.Security].includes(VIEWS[i].id)) VIEWS.splice(i, 1)
  }
  for (const view of VIEWS) view.routes = view.routes.filter(route => !isAdvancedPath(route.to))
}
`)

const panelPath = 'src/components/sidebar/panel.tsx'
patch(panelPath, ': favorite.accountId === accountId,', ': favorite.accountId === accountId && (advancedFeaturesEnabled() || !isAdvancedPath(favorite.path)),')
writeFileSync(panelPath, 'import { advancedFeaturesEnabled, isAdvancedPath } from "@/lib/license-advanced"\n' + readFileSync(panelPath, 'utf8'))

const checkoutPath = 'src/components/machines/form/check-out.tsx'
patch(checkoutPath, 'options={INCLUDE_OPTIONS}', 'options={INCLUDE_OPTIONS.filter(option => advancedFeaturesEnabled() || ["license", "license.entitlements"].includes(option.value))}')
patch(checkoutPath, 'include: [],', 'include: ["license", "license.entitlements"],')
writeFileSync(checkoutPath, 'import { advancedFeaturesEnabled } from "@/lib/license-advanced"\n' + readFileSync(checkoutPath, 'utf8'))

const machinePath = 'src/pages/app/machine/details.tsx'
const machineSource = readFileSync(machinePath, 'utf8').replaceAll('\r\n', '\n')
const componentField = /<Attribute\.Field\s+variant="text"\s+label="(?:Components|Processes)"\s+value=\{\s*<GoToButton[\s\S]*?\/>\s*\}\s*\/>/g
if (!componentField.test(machineSource)) throw new Error('Machine component link changed')
writeFileSync(machinePath, 'import { advancedFeaturesEnabled } from "@/lib/license-advanced"\n' + machineSource.replace(componentField, '{advancedFeaturesEnabled() && ($&)}'))

for (const resource of ['license', 'machine', 'user']) {
  const file = `src/pages/app/${resource}/details.tsx`
  let source = readFileSync(file, 'utf8')
  const groupField = /<Attribute\.Field\s+variant="text"\s+label="Group"\s+value=\{\s*<ResourceLink[\s\S]*?\/>\s*\}\s*\/>/
  if (!groupField.test(source)) throw new Error(`Group detail link changed: ${file}`)
  source = source.replace(groupField, '{advancedFeaturesEnabled() && ($&)}')
  if (!source.includes('import { advancedFeaturesEnabled }')) source = 'import { advancedFeaturesEnabled } from "@/lib/license-advanced"\n' + source
  writeFileSync(file, source)
}

for (const resource of ['licenses', 'machines', 'users']) {
  const file = `src/components/${resource}/form/fields.tsx`
  const source = readFileSync(file, 'utf8')
  const groupField = /<GroupIdField\s[\s\S]*?\/>/
  if (!groupField.test(source)) throw new Error(`Group form field changed: ${file}`)
  writeFileSync(file, 'import { AdvancedFeaturesSection } from "@/components/license-advanced"\n' + source.replace(groupField, '<AdvancedFeaturesSection key="groupId">$&</AdvancedFeaturesSection>'))
  const filterFile = `src/components/${resource}/filter-bar.tsx`
  const filterSource = readFileSync(filterFile, 'utf8')
  const groupFilter = /<Filters\.ResourceFilter\s+label="Group"[\s\S]*?\/>/
  if (!groupFilter.test(filterSource)) throw new Error(`Group filter changed: ${filterFile}`)
  // Existing bookmarked filters remain visible so users can clear them.
  writeFileSync(filterFile, 'import { advancedFeaturesEnabled } from "@/lib/license-advanced"\n' + filterSource.replace(groupFilter, '{(advancedFeaturesEnabled() || filters.group != null) && ($&)}'))
}

// Retain values in react-hook-form; only remove unconsumed controls from the
// basic view. Required fingerprint, expiry, machine and process limits stay.
for (const resource of ['licenses', 'policies']) {
  const file = `src/components/${resource}/form/fields.tsx`
  patch(file, 'fields.map((field) => {', 'fields.filter(field => advancedFeaturesEnabled() || !["maxCores", "maxMemory", "maxDisk", "maxUses", "maxUsers", "usePool", "requireChecksumScope", "requireComponentsScope", "requireUserScope", "requireVersionScope", "componentMatchingStrategy", "componentUniquenessStrategy", "processLeasingStrategy"].includes(field)).map((field) => {')
  writeFileSync(file, 'import { advancedFeaturesEnabled } from "@/lib/license-advanced"\n' + readFileSync(file, 'utf8'))
}

// SBOMScan imports a Machine File. Its generic License File and metered-use
// reset actions are reserved for integrations that actually consume them.
const licenseDetailsPath = 'src/pages/app/license/details.tsx'
let licenseDetails = readFileSync(licenseDetailsPath, 'utf8')
for (const permission of ['license.check-out', 'license.usage.reset']) {
  const block = new RegExp(`<Can permission="${permission.replaceAll('.', '\\.')}">[\\s\\S]*?<\\/Can>`, 'g')
  if (!block.test(licenseDetails)) throw new Error(`License action changed: ${permission}`)
  licenseDetails = licenseDetails.replace(block, '{advancedFeaturesEnabled() && ($&)}')
}
writeFileSync(licenseDetailsPath, licenseDetails)

// Gate parent pages as well as the navigation. Keep all content hooks in a
// separate component so the preference never changes React's hook ordering.
for (const page of ['groups', 'components', 'processes', 'packages', 'releases', 'artifacts', 'platforms', 'arches', 'channels', 'engines', 'webhook-endpoints', 'webhook-events', 'tokens', 'event-logs', 'request-logs', 'teams', 'learn', 'settings/permissions', 'settings/developers', 'settings/billing']) {
  const pagePath = `src/pages/app/${page}.tsx`
  const source = readFileSync(pagePath, 'utf8')
  const match = source.match(/export default function (\w+)\(\)/)
  if (!match) throw new Error(`Advanced page component changed: ${pagePath}`)
  const name = match[1]
  writeFileSync(pagePath, 'import { advancedFeaturesEnabled } from "@/lib/license-advanced"\nimport { AdvancedFeaturesPrompt } from "@/components/license-advanced"\n' + source.replace(match[0], `export default function ${name}() {\n  return advancedFeaturesEnabled() ? <${name}AdvancedContent /> : <AdvancedFeaturesPrompt />\n}\n\nfunction ${name}AdvancedContent()`))
}

// The command palette has its own action catalogue, not only sidebar routes.
const palettePath = 'src/lib/palette.ts'
patch(palettePath, 'return all.filter((c) => opts.isCloud || !c.cloudOnly)', `return all.filter((c) => (opts.isCloud || !c.cloudOnly) && (advancedFeaturesEnabled() || (
    c.kind === "navigate" ? !isAdvancedPath(c.to) :
    c.kind === "find" ? !isAdvancedResource(c.resource) :
    c.kind === "preset" ? !isAdvancedResource(c.preset.type) :
    c.kind === "create" ? ![DialogKey.Group, DialogKey.Package, DialogKey.Release].includes(c.dialog) :
    c.id !== "help:api"
  )))`)
writeFileSync(palettePath, 'import { advancedFeaturesEnabled, isAdvancedPath, isAdvancedResource } from "@/lib/license-advanced"\n' + readFileSync(palettePath, 'utf8'))
const paletteHomePath = 'src/components/palette/home.tsx'
patch(paletteHomePath, '? true\n', '? advancedFeaturesEnabled() || !isAdvancedResource(r.resource)\n')
writeFileSync(paletteHomePath, 'import { advancedFeaturesEnabled, isAdvancedResource } from "@/lib/license-advanced"\n' + readFileSync(paletteHomePath, 'utf8'))

const onboardingPath = 'src/components/sidebar/notice/onboarding.tsx'
patch(onboardingPath, '  const eligible =\n    !dismissed', '  const eligible =\n    advancedFeaturesEnabled() &&\n    !dismissed')
writeFileSync(onboardingPath, 'import { advancedFeaturesEnabled } from "@/lib/license-advanced"\n' + readFileSync(onboardingPath, 'utf8'))

const generalPath = 'src/pages/app/settings/general.tsx'
patch(generalPath, '                <Attribute.Field\n                  label="Theme"', '                <Attribute.Field\n                  label="Advanced features"\n                  variant="none"\n                  value={<AdvancedFeaturesToggle />}\n                />\n                <Attribute.Field\n                  label="Theme"')
writeFileSync(generalPath, 'import { AdvancedFeaturesToggle } from "@/components/license-advanced"\n' + readFileSync(generalPath, 'utf8'))
