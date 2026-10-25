import { useState } from "react"
import { z } from "zod"
import translations from "./license-locales/zh-TW.json"

export type Language = "zh-TW" | "en"
const LANGUAGE_KEY = "app_language"

export function language(): Language {
  try { return localStorage.getItem(LANGUAGE_KEY) === "en" ? "en" : "zh-TW" }
  catch { return "zh-TW" }
}

const entities: Record<string, string> = {
  "&nbsp;": "\u00a0", "&apos;": "'", "&quot;": '"', "&amp;": "&",
  "&lt;": "<", "&gt;": ">", "&ldquo;": "“", "&rdquo;": "”", "&times;": "×",
}
export function t(english: string, values: unknown[] = []): string {
  const dictionary = translations as Record<string, string>
  const text = language() === "zh-TW" ? dictionary[english] ?? english : english
  return text.replace(/&(?:nbsp|apos|quot|amp|lt|gt|ldquo|rdquo|times);/g, entity => entities[entity])
    .replace(/\{(\d+)\}/g, (_, index: string) => String(values[Number(index)] ?? ""))
}

// Translate display errors without changing API payloads, codes, or field pointers.
export function errorText(english: string, code?: string): string {
  if (language() === "en") return english
  const known = t(english)
  if (known !== english) return known
  const exact: Record<string, string> = {
    "is invalid": "格式無效", "is missing": "缺少此值", "must exist": "此項目必須存在",
    "must be present": "此欄位為必填項目", "can't be blank": "此欄位不可留空",
    "cannot be blank": "此欄位不可留空", "has already been taken": "此值已被使用",
    "must be a valid uuid": "必須為有效的 UUID", "is not allowed": "不允許此操作",
    "must be greater than 0": "必須大於 0", "must be a valid url": "必須為有效網址",
  }
  const normalized = english.trim().replace(/[.]$/, "").toLowerCase()
  if (exact[normalized]) return exact[normalized]
  if (/_TAKEN$/.test(code || "")) return "此值已被使用"
  if (/_NOT_FOUND$/.test(code || "")) return "找不到指定的資源"
  if (/_EXPIRED$/.test(code || "")) return "已到期，請重新確認有效期限"
  if (/_REQUIRED$/.test(code || "")) return "缺少必要欄位"
  return english
}

const originalErrorMap = z.getErrorMap()
z.setErrorMap((issue, context) => {
  if (language() === "en") return originalErrorMap(issue, context)
  if (issue.code === "invalid_type") return { message: issue.received === "undefined" ? "此欄位為必填項目" : "資料類型不正確" }
  if (issue.code === "invalid_string") return { message: "格式無效，請檢查輸入內容" }
  if (issue.code === "invalid_enum_value") return { message: "請選擇有效的選項" }
  if (issue.code === "too_small") return { message: `輸入值至少需為 ${issue.minimum}` }
  if (issue.code === "too_big") return { message: `輸入值最多可為 ${issue.maximum}` }
  return { message: errorText(context.defaultError) }
})

document.documentElement.lang = language() === "en" ? "en-US" : "zh-Hant-TW"

export function LanguageSwitcher() {
  const [selected, setSelected] = useState(language)
  return (
    <div className="flex max-w-sm flex-col gap-2 text-sm text-content" data-testid="language-switcher">
      <label htmlFor="license-language" className="sr-only">{t("Language")}</label>
      <select id="license-language" value={selected} className="h-8 cursor-pointer rounded-md border border-accent bg-background px-2 text-content outline-none focus-visible:ring-2 focus-visible:ring-primary" onChange={event => {
        const next = event.target.value as Language
        try { localStorage.setItem(LANGUAGE_KEY, next) } catch { return }
        setSelected(next)
        window.location.reload()
      }}>
        <option value="zh-TW">繁體中文（台灣）</option>
        <option value="en">English (United States)</option>
      </select>
      <p className="text-xs text-content-muted">{t("Save any changes before switching languages. This page will reload.")}</p>
    </div>
  )
}
