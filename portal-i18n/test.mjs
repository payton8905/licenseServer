import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import vm from 'node:vm'
import { execFileSync } from 'node:child_process'
import { createRequire } from 'node:module'
import ts from 'typescript'

const dictionary = JSON.parse(fs.readFileSync(new URL('./zh-TW.json', import.meta.url), 'utf8'))
for (const [english, chinese] of Object.entries(dictionary)) {
  assert.ok(chinese.length, `Empty translation: ${english}`)
  const tokens = value => [...value.matchAll(/\{\d+\}/g)].map(m => m[0]).sort()
  assert.deepEqual(tokens(chinese), tokens(english), `Interpolation mismatch: ${english}`)
}

const module = { exports: {} }
let saved = null
const runtime = fs.readFileSync(new URL('./runtime.tsx', import.meta.url), 'utf8')
const compiled = ts.transpileModule(runtime, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
}}).outputText
const require = createRequire(import.meta.url)
const document = { documentElement: { lang: '' } }
vm.runInNewContext(compiled, {
  module, exports: module.exports, document,
  localStorage: { getItem: () => saved },
  require: name => name.endsWith('zh-TW.json') ? dictionary : require(name),
})
const { t, language, errorText } = module.exports
assert.equal(language(), 'zh-TW')
assert.equal(document.documentElement.lang, 'zh-Hant-TW')
assert.equal(t('License'), '授權')
assert.equal(t('Row {0}: {1}', [2, 'Basic &amp; Pro']), '第 2 列：Basic &amp; Pro')
assert.equal(t('Customer-defined name'), 'Customer-defined name')
assert.equal(errorText('Has already been taken', 'EMAIL_TAKEN'), '此值已被使用')
saved = 'en'
assert.equal(errorText('Has already been taken', 'EMAIL_TAKEN'), 'Has already been taken')
assert.equal(t('License'), 'License')
assert.equal(t('Can&apos;t scan the QR code? Enter this secret key into your authenticator app or password manager instead.'), "Can't scan the QR code? Enter this secret key into your authenticator app or password manager instead.")
saved = 'invalid'
assert.equal(language(), 'zh-TW')

const fixtureRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'license-i18n-test-'))
const file = path.join(fixtureRoot, 'fixture.tsx')
fs.writeFileSync(file, [
  'type Status = "Active" | "Inactive";',
  'const endpoint = { path: "/licenses", method: "GET", value: "Active", id: "License", name: "SBOMScan" };',
  'const sampleAttributeTypeSchema = { description: "string", status: "enum" };',
  'const StatusLabels = { ACTIVE: "Active", INACTIVE: "Inactive" };',
  'const StatusDescriptions = { status: "The status of the user." };',
  'const view = <><h1>Licenses</h1><input placeholder="Enter name..." /><p>{`Row ${2}: ${"Basic"}`}</p></>;',
].join('\n'))
execFileSync(process.execPath, [new URL('./transform.mjs', import.meta.url).pathname, fixtureRoot], { stdio: 'pipe' })
const transformed = fs.readFileSync(file, 'utf8')
assert.match(transformed, /licenseT\("Licenses"\)/)
assert.match(transformed, /ACTIVE: licenseT\("Active"\)/)
assert.match(transformed, /status: licenseT\("The status of the user\."\)/)
assert.match(transformed, /licenseT\("Row \{0\}: \{1\}", \[2, "Basic"\]\)/)
assert.match(transformed, /description: "string", status: "enum"/)
assert.match(transformed, /value: "Active", id: "License", name: "SBOMScan"/)
assert.match(transformed, /type Status = "Active" \| "Inactive"/)
console.log(`PASS: ${Object.keys(dictionary).length} translations, interpolation, language fallback, JSX, and API/data boundaries.`)

const quotaModule = { exports: {} }
const quotaCompiled = ts.transpileModule(fs.readFileSync(new URL('./project-quota.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText
vm.runInNewContext(quotaCompiled, { module: quotaModule, exports: quotaModule.exports })
const { projectQuotaMetadata } = quotaModule.exports
assert.equal(projectQuotaMetadata({}, { max_projects: 3 }).max_projects, 3)
assert.equal(projectQuotaMetadata({ max_projects: 5 }, { max_projects: 3 }).max_projects, 5)
assert.equal(projectQuotaMetadata({ max_projects: -1 }).max_projects, -1)
assert.equal(projectQuotaMetadata({ maxProjects: 7 }).max_projects, 7)
assert.equal(projectQuotaMetadata({ max_projects: 5, concurrent_users: 10 }).concurrent_users, 10)
for (const value of [undefined, null, 0, -2, true, 1.5, '5', 2147483648]) {
  assert.throws(() => projectQuotaMetadata({ max_projects: value }))
}
assert.throws(() => projectQuotaMetadata({}))
assert.throws(() => projectQuotaMetadata({ max_projects: 3, maxProjects: -1 }))
console.log('PASS: project quota defaults, per-license overrides, explicit unlimited and invalid quota rejection.')
