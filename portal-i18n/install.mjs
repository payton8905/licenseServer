import fs from 'node:fs'
import { execFileSync } from 'node:child_process'

// Keep the upstream checkout pinned. Changes to its integration points fail the build.
execFileSync(process.execPath, ['/app/license-localization/transform.mjs', 'src'], { stdio: 'inherit' })
fs.mkdirSync('src/license-locales', { recursive: true })
fs.copyFileSync('/app/license-localization/zh-TW.json', 'src/license-locales/zh-TW.json')
fs.copyFileSync('/app/license-localization/runtime.tsx', 'src/license-i18n.tsx')

function patch(file, from, to) {
  const source = fs.readFileSync(file, 'utf8')
  if (!source.includes(from)) throw new Error(`Localization integration changed: ${file}: ${from}`)
  fs.writeFileSync(file, source.replace(from, to))
}
patch('src/pages/app/settings/general.tsx', 'import { useEffect, useState } from "react"', 'import { useEffect, useState } from "react"\nimport { LanguageSwitcher } from "@/license-i18n"')
patch('src/pages/app/settings/general.tsx', '<Attribute.Field\n                  label={licenseT("Theme")}', '<Attribute.Field\n                  label={licenseT("Language")}\n                  variant="none"\n                  value={<LanguageSwitcher />}\n                />\n                <Attribute.Field\n                  label={licenseT("Theme")}')
patch('src/components/documentation-link.tsx', '[page || "Keygen"]', '[licenseT(page || "Keygen")]')
const formErrorsPath = 'src/lib/form-errors.ts'
let formErrors = fs.readFileSync(formErrorsPath, 'utf8')
formErrors = 'import { errorText as localizedErrorText } from "@/license-i18n"\n' + formErrors
formErrors = formErrors.replace(/capitalize\(apiError\.detail \?\? (licenseT\("Field is invalid"\)|apiError\.message)\)/g, 'localizedErrorText(capitalize(apiError.detail ?? $1), apiError.code)')
fs.writeFileSync(formErrorsPath, formErrors)

// Date-fns otherwise defaults to English even when the interface is Chinese.
let timestamps = fs.readFileSync('src/lib/timestamps.ts', 'utf8')
timestamps = 'import { zhTW, enUS } from "date-fns/locale"\nimport { language as licenseLanguage } from "@/license-i18n"\n' + timestamps
timestamps = timestamps.replace('{ addSuffix: true }', '{ addSuffix: true, locale: licenseLanguage() === "zh-TW" ? zhTW : enUS }')
timestamps = timestamps.replace('{ format, delimiter: ", " }', '{ format, delimiter: licenseLanguage() === "zh-TW" ? "、" : ", ", locale: licenseLanguage() === "zh-TW" ? zhTW : enUS }')
timestamps = timestamps.replace('return future ? `in ${body}` : `${body} ago`', 'return licenseLanguage() === "zh-TW" ? (future ? `${body}後` : `${body}前`) : (future ? `in ${body}` : `${body} ago`)')
timestamps = timestamps.replaceAll('new Intl.DateTimeFormat("en-US",', 'new Intl.DateTimeFormat(licenseLanguage() === "zh-TW" ? "zh-TW" : "en-US",')
timestamps = timestamps.replace('date: `${valueFor("month")} ${valueFor("day")}, ${valueFor("year")}`', 'date: licenseLanguage() === "zh-TW" ? `${valueFor("year")}年${valueFor("month")}${valueFor("day")}日` : `${valueFor("month")} ${valueFor("day")}, ${valueFor("year")}`')
timestamps = timestamps.replace('export const DATE_FORMAT = "MM/dd/yyyy"', 'export const DATE_FORMAT = licenseLanguage() === "zh-TW" ? "yyyy/MM/dd" : "MM/dd/yyyy"')
fs.writeFileSync('src/lib/timestamps.ts', timestamps)

const calendarPath = 'src/components/ui/calendar.tsx'
let calendar = fs.readFileSync(calendarPath, 'utf8')
calendar = 'import { zhTW, enUS } from "date-fns/locale"\nimport { language as licenseLanguage } from "@/license-i18n"\n' + calendar
calendar = calendar.replace('<DayPicker\n', '<DayPicker\n      locale={licenseLanguage() === "zh-TW" ? zhTW : enUS}\n')
calendar = calendar.replace('date.toLocaleString("default",', 'date.toLocaleString(licenseLanguage() === "zh-TW" ? "zh-TW" : "en-US",')
fs.writeFileSync(calendarPath, calendar)
