import { readFileSync, writeFileSync } from 'node:fs'

const path = 'src/schemas/auth.ts'
let source = readFileSync(path, 'utf8').replaceAll('\r\n', '\n')
const original = 'export const LoginSchema = z.object({\n  email: z.string().email("Please enter a valid email."),\n})'
if (!source.includes(original)) throw new Error('Portal LoginSchema changed; review admin alias patch.')
source = source.replace(original, `export const LoginSchema = z.object({
  email: z.string().trim()
    .transform((value) => value.toLowerCase() === "admin" ? import.meta.env.VITE_ADMIN_EMAIL : value)
    .pipe(z.string().email("Please enter admin or a valid email.")),
})`)
writeFileSync(path, source)

const fieldsPath = 'src/components/auth/form/fields.tsx'
const fields = readFileSync(fieldsPath, 'utf8').replaceAll('\r\n', '\n')
if (!fields.includes('placeholder="Enter email..."')) throw new Error('Portal email field changed.')
writeFileSync(fieldsPath, fields.replace('placeholder="Enter email..."', 'placeholder="admin / email"'))

// Merge the email/password steps while retaining upstream OTP and SSO handling.
const loginPath = 'src/components/auth/form/login.tsx'
let login = readFileSync(loginPath, 'utf8').replaceAll('\r\n', '\n')
function replaceLogin(from, to) {
  if (!login.includes(from)) throw new Error(`Portal login integration changed: ${from}`)
  login = login.replace(from, to)
}
replaceLogin('type Step = "email" | "password" | "verify" | "sso"', 'type Step = "email" | "verify" | "sso"')
replaceLogin('["email", "password", "verify", "sso"]', '["email", "verify", "sso"]')
const passwordBranchStart = login.indexOf('{step === "password" ? (')
const verifyBranchStart = login.indexOf(') : step === "verify" ? (', passwordBranchStart)
if (passwordBranchStart < 0 || verifyBranchStart < 0) throw new Error('Portal login steps changed.')
login = login.slice(0, passwordBranchStart) + '{step === "verify" ? (' + login.slice(verifyBranchStart + ') : step === "verify" ? ('.length)
replaceLogin('onPasswordInvalid={() => setStep("password")}', 'onPasswordInvalid={() => { setPassword(""); setStep("email") }}')
replaceLogin(`          onPasswordRequired={(value) => {
            setEmail(value)
            setStep("password")
          }}`, `          onOtpRequired={(emailValue, passwordValue, rememberValue) => {
            setEmail(emailValue)
            setPassword(passwordValue)
            setRemember(rememberValue)
            setStep("verify")
          }}
          onAuthenticated={onSubmit}`)
replaceLogin('  onPasswordRequired,', '  onOtpRequired,\n  onAuthenticated,')
replaceLogin('  onPasswordRequired: (email: string) => void', '  onOtpRequired: (email: string, password: string, remember: boolean) => void\n  onAuthenticated: (data: AuthData, remember: boolean) => void')
replaceLogin('  const form = useForm<Schemas.Auth.LoginValues>({\n    resolver: zodResolver(Schemas.Auth.LoginSchema),', '  const credentialsSchema = Schemas.Auth.LoginSchema.merge(Schemas.Auth.PasswordSchema)\n  type Credentials = Schemas.Auth.LoginValues & Schemas.Auth.PasswordValues\n  const form = useForm<Credentials>({\n    resolver: zodResolver(credentialsSchema),')
replaceLogin('    defaultValues: { email },', '    defaultValues: { email, password: "", remember: true },')
replaceLogin('async function onSubmit({ email }: Schemas.Auth.LoginValues)', 'async function onSubmit({ email, password, remember }: Credentials)')
replaceLogin('const { errors } = await keygen.authenticate({ email })', 'const { data, errors } = await keygen.authenticate({ email, password })')
replaceLogin('        throw new Error("Service is unavailable.")', '        if (!data) throw new Error("Service is unavailable.")\n        onAuthenticated(data, remember)\n        return')
replaceLogin(`        case AuthErrorCode.PasswordRequired:
          onPasswordRequired(email)
          break`, `        case AuthErrorCode.PasswordInvalid:
        case AuthErrorCode.PasswordRequired:
          form.setError("password", { type: "manual", message: "Invalid password. Please try again." })
          break
        case AuthErrorCode.OtpRequired:
          onOtpRequired(email, password, remember)
          break`)
replaceLogin('<Auth.Form.Fields include={["email"]} autoFocus="email" />', '<Auth.Form.Fields include={["email", "password", "remember"]} autoFocus="email" />')
replaceLogin('                "Continue"', '                "Sign in"')
const passwordStepStart = login.indexOf('function PasswordStep(')
const verifyStepStart = login.indexOf('function VerifyStep(', passwordStepStart)
if (passwordStepStart < 0 || verifyStepStart < 0) throw new Error('Portal password component changed.')
login = login.slice(0, passwordStepStart) + login.slice(verifyStepStart)
// cn was only used by the removed separate password step.
login = login.replace('import { cn } from "@/lib/utils"\n', '')
writeFileSync(loginPath, login)

// This self-hosted CE console does not advertise hosted/EE upgrades.
// Keep all edition checks and API permissions intact.
writeFileSync('src/components/permissions/upgrade.tsx', `export default function PermissionsUpgrade() {
  return null
}
`)
for (const [folder, component, message] of [
  ['event-logs', 'EventLogsUpgrade', 'Event logs are unavailable in this installation.'],
  ['request-logs', 'RequestLogsUpgrade', 'Request logs are unavailable in this installation.'],
]) {
  writeFileSync(`src/components/${folder}/upgrade.tsx`, `import type { ReactNode } from "react"
export default function ${component}({ className }: { children: ReactNode; className?: string }) {
  return <div className={className}><p className="p-4 text-sm text-content-subdued">${message}</p></div>
}
`)
}
writeFileSync('src/components/sidebar/notice/billing.tsx', `export default function SidebarNoticeBilling() {
  return null
}
`)
const dashboardPath = 'src/components/analytics/dashboard.tsx'
let dashboard = readFileSync(dashboardPath, 'utf8').replaceAll('\r\n', '\n')
function replaceDashboard(from, to) {
  if (!dashboard.includes(from)) throw new Error(`Portal dashboard integration changed: ${from}`)
  dashboard = dashboard.replace(from, to)
}
function removeDashboardFunction(name, nextName) {
  const start = dashboard.indexOf(`function ${name}(`)
  const end = dashboard.indexOf(`function ${nextName}(`, start)
  if (start < 0 || end < 0) throw new Error(`Portal dashboard function changed: ${name}`)
  dashboard = dashboard.slice(0, start) + dashboard.slice(end)
}
removeDashboardFunction('UpgradeButton', 'AnalyticsPermissionLockedOverlay')
removeDashboardFunction('AnalyticsUpgrade', 'RequestUsageSummary')
replaceDashboard('import { Button } from "@/components/ui/button"\n', '')
replaceDashboard('import { PRICING_URL } from "@/lib/url"\n', '')
replaceDashboard('  upgradeRequired,\n', '')
replaceDashboard('  upgradeRequired: boolean\n', '')
replaceDashboard('      upgradeRequired={isFreePlan}\n', '')
replaceDashboard(`  const hasLockedAnalytics =
    !canUseActivity || !canUseEvents || !canUseLeaderboards
  const shouldShowAnalyticsUpgrade =
    hasLockedAnalytics && activityVisibility.hasEntered
`, '')
replaceDashboard(`        {shouldShowAnalyticsUpgrade && (
          <AnalyticsUpgrade upgradeRequired={upgradeRequired} />
        )}
`, '')
// Unavailable analytics must not look like charts still waiting to load.
for (const [section, capability] of [['activity', 'canUseActivity'], ['event', 'canUseEvents'], ['leaderboard', 'canUseLeaderboards']]) {
  const startMarker = `<section ref={${section}Visibility.ref}`
  const start = dashboard.indexOf(startMarker)
  const end = dashboard.indexOf('</section>', start)
  if (start < 0 || end < 0) throw new Error(`Portal analytics section changed: ${section}`)
  dashboard = dashboard.slice(0, start) + `{${capability} && (` + dashboard.slice(start, end + '</section>'.length) + ')}' + dashboard.slice(end + '</section>'.length)
}
writeFileSync(dashboardPath, dashboard)

// Home is a destination as well as a sidebar category.
const sidebarPath = 'src/components/sidebar/panel.tsx'
let sidebar = readFileSync(sidebarPath, 'utf8').replaceAll('\r\n', '\n')
function replaceSidebar(from, to) {
  if (!sidebar.includes(from)) throw new Error(`Portal sidebar integration changed: ${from}`)
  sidebar = sidebar.replace(from, to)
}
replaceSidebar('import { Link, useLocation, useMatchRoute }', 'import { Link, useLocation, useMatchRoute, useNavigate }')
replaceSidebar('  const activeView = useActiveView()', '  const navigate = useNavigate()\n  const activeView = useActiveView()')
replaceSidebar(`                      setSelectedView(view)
                      setOpen(true)`, `                      setSelectedView(view)
                      setOpen(true)
                      if (view.id === ViewId.Home) {
                        void navigate({ to: "/$accountId/app/dashboard", params: { accountId } })
                      }`)
replaceSidebar('                    variant="rail"\n                    size="rail"', '                    aria-label={view.label}\n                    variant="rail"\n                    size="rail"')
replaceSidebar('<SidebarGroupLabel>{currentView.label}</SidebarGroupLabel>', `{currentView.id === ViewId.Home ? (
                    <SidebarGroupLabel asChild className="cursor-pointer hover:bg-background-2">
                      <Link to="/$accountId/app/dashboard" params={{ accountId }}>
                        {currentView.label}
                      </Link>
                    </SidebarGroupLabel>
                  ) : (
                    <SidebarGroupLabel>{currentView.label}</SidebarGroupLabel>
                  )}`)
writeFileSync(sidebarPath, sidebar)

// The clickable Home heading replaces the duplicate Metrics menu item.
const viewsPath = 'src/lib/views.ts'
const views = readFileSync(viewsPath, 'utf8').replaceAll('\r\n', '\n')
const metricsRoute = `      {
        to: "/$accountId/app/dashboard",
        label: "Metrics",
        params: { accountId: keygen.config.id },
      },
`
if (!views.includes(metricsRoute)) throw new Error('Portal Metrics navigation changed.')
writeFileSync(viewsPath, views.replace(metricsRoute, ''))

// A failed HTTPS request must not leave the wizard looking unresponsive.
const wizardPath = 'src/components/forms/layout/wizard.tsx'
let wizard = readFileSync(wizardPath, 'utf8').replaceAll('\r\n', '\n')
const wizardCatch = `        } catch (error) {
          if (errorMessage && error instanceof APIError) {`
if (!wizard.includes(wizardCatch)) throw new Error('Portal wizard error handling changed.')
wizard = wizard.replace('import { handleFormError } from "@/lib/form-errors"', 'import { handleFormError } from "@/lib/form-errors"\nimport { toast } from "@/lib/toast"')
wizard = wizard.replace(wizardCatch, `        } catch (error) {
          if (!(error instanceof APIError)) {
            toast({
              message: errorMessage ?? "Failed to submit",
              description: "Unable to connect. Check your connection and the server certificate, then try again.",
              variant: "error",
            })
          }
          if (errorMessage && error instanceof APIError) {`)
writeFileSync(wizardPath, wizard)

// Download the gateway's active public CA; no certificate is baked into the image.
const securityPath = 'src/pages/app/settings/security.tsx'
let security = readFileSync(securityPath, 'utf8').replaceAll('\r\n', '\n')
const securityGrid = '<div className="grid w-full max-w-5xl grid-cols-1 gap-x-16 gap-y-8 md:grid-cols-[1fr_2fr]">'
if (!security.includes(securityGrid)) throw new Error('Portal security layout changed.')
security = security.replace(securityGrid, `${securityGrid}
            <div className="flex flex-col space-y-2">
              <h2 className="font-owners-wide text-lg text-content-loud">Local HTTPS certificate</h2>
              <p className="font-owners-text text-sm text-content-muted">Download the local CA certificate to trust this license server on your computer.</p>
            </div>
            <div className="space-y-4 rounded border border-accent bg-background p-4 shadow-sm dark:border-none dark:bg-background-1">
              <Button asChild variant="outline">
                <a href="/local-ca.crt" download="keygen-local-ca.crt">Download local CA certificate</a>
              </Button>
              <ol className="list-decimal space-y-2 pl-5 text-sm text-content-muted">
                <li>On Windows, open the downloaded certificate and choose Install Certificate, then Current User.</li>
                <li>Choose Place all certificates in the following store, then Trusted Root Certification Authorities, and complete the import.</li>
                <li>Close all Chrome windows, reopen the browser, and return to this site.</li>
              </ol>
              <p className="text-sm text-content-muted">Downloading does not install or trust the certificate automatically. Complete the trust settings on your computer.</p>
            </div>`)
writeFileSync(securityPath, security)

// Vendor controls for signed per-license project quotas.
writeFileSync('src/components/project-quota.tsx', readFileSync('/app/license-localization/project-quota.tsx', 'utf8'))
writeFileSync('src/lib/project-quota.ts', readFileSync('/app/license-localization/project-quota.ts', 'utf8'))
for (const resource of ['licenses', 'policies']) {
  const fieldsFile = `src/components/${resource}/form/fields.tsx`
  let fieldsSource = readFileSync(fieldsFile, 'utf8').replaceAll('\r\n', '\n')
  const marker = 'function MetadataField('
  const start = fieldsSource.indexOf(marker)
  if (start < 0) throw new Error(`Portal metadata field changed: ${resource}`)
  const tail = fieldsSource.slice(start)
  const target = '        <FormItem>\n          <MetadataInput'
  if (!tail.includes(target)) throw new Error(`Portal metadata input changed: ${resource}`)
  fieldsSource = fieldsSource.slice(0, start) + tail.replace(target, '        <FormItem>\n          <ProjectQuotaField />\n          <MetadataInput')
  writeFileSync(fieldsFile, 'import { ProjectQuotaField } from "@/components/project-quota"\n' + fieldsSource)
}
const licenseQueriesPath = 'src/queries/licenses.ts'
let licenseQueries = readFileSync(licenseQueriesPath, 'utf8').replaceAll('\r\n', '\n')
const createMarker = '      const response = await keygen.licenses.create(values, {'
if (!licenseQueries.includes(createMarker)) throw new Error('Portal license creation changed.')
licenseQueries = licenseQueries.replace(createMarker, `      try {
        const metadata = values.metadata as Record<string, unknown> | undefined
        const needsDefault = !Object.prototype.hasOwnProperty.call(metadata ?? {}, "max_projects") && !Object.prototype.hasOwnProperty.call(metadata ?? {}, "maxProjects")
        const policy = needsDefault ? (await keygen.policies.get({ id: values.policyId })).data : undefined
        values = { ...values, metadata: projectQuotaMetadata(metadata, policy?.attributes.metadata) }
      } catch (error) {
        throw new APIError({ title: "Invalid project quota", detail: error instanceof Error ? error.message : "Invalid project quota", code: "PROJECT_QUOTA_INVALID", source: { pointer: "/data/attributes/metadata" } })
      }
      const response = await keygen.licenses.create(values, {`)
const updateMarker = '        const changes = diff('
if (!licenseQueries.includes(updateMarker)) throw new Error('Portal license update changed.')
licenseQueries = licenseQueries.replace(updateMarker, `        try {
          attributes.metadata = projectQuotaMetadata((attributes.metadata ?? current.attributes.metadata) as Record<string, unknown>)
        } catch (error) {
          throw new APIError({ title: "Invalid project quota", detail: error instanceof Error ? error.message : "Invalid project quota", code: "PROJECT_QUOTA_INVALID", source: { pointer: "/data/attributes/metadata" } })
        }
        const changes = diff(`)
writeFileSync(licenseQueriesPath, 'import { projectQuotaMetadata } from "@/lib/project-quota"\n' + licenseQueries)
