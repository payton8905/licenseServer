import fs from 'node:fs'
import path from 'node:path'
import ts from 'typescript'

const root = process.argv[2] || 'src'
const extract = process.argv.includes('--extract')
const dictionaryPath = new URL('./zh-TW.json', import.meta.url)
const dictionary = fs.existsSync(dictionaryPath) ? JSON.parse(fs.readFileSync(dictionaryPath, 'utf8')) : {}
const found = new Map()
const displayKeys = /^(?:label|title|description|message|detail|tooltip|placeholder|alt|aria-label|heading|text|header|caption|children|help|displayName|name|prefix|suffix|crumb|headline|subtitle|[A-Za-z]*(?:Label|Text|Title|Description|Message|Placeholder))$/
const excludedKeys = /^(?:value|id|key|code|type|method|status|role|scope|event|path|to|href|url|className|variant|size|name|accessorKey|accessor|endpoint|auth|permission|permissions|field|fields|data-testid)$/

function displayMap(node) {
  for (let p = node.parent; p; p = p.parent) {
    if (ts.isVariableDeclaration(p)) return /(?:Labels|Descriptions|Titles|Messages|Names|Views|Steps|Actions|Options)$/.test(p.name.getText())
    if (ts.isFunctionLike(p)) break
  }
  return false
}

function descriptionMap(node) {
  for (let p = node.parent; p; p = p.parent) {
    if (ts.isVariableDeclaration(p)) return /Descriptions$/.test(p.name.getText())
    if (ts.isFunctionLike(p)) break
  }
  return false
}

function cleanJsx(text) {
  const lines = text.split(/\r\n|\n|\r/)
  let last = 0
  lines.forEach((line, i) => { if (/[^ \t]/.test(line)) last = i })
  return lines.map((line, i) => {
    let value = line.replace(/\t/g, ' ')
    if (i !== 0) value = value.replace(/^ +/, '')
    if (i !== lines.length - 1) value = value.replace(/ +$/, '')
    return value && i !== last ? value + ' ' : value
  }).join('')
}

function protectedContext(node) {
  for (let p = node.parent; p; p = p.parent) {
    if (ts.isImportDeclaration(p) || ts.isExportDeclaration(p) || ts.isTypeNode(p)) return true
    if (ts.isVariableDeclaration(p) && /AttributeTypeSchema$/.test(p.name.getText())) return true
    if (ts.isJsxAttribute(p)) return !displayKeys.test(p.name.getText()) || p.name.getText() === 'name'
    if (ts.isPropertyAssignment(p) && p.initializer === node) {
      if (descriptionMap(node)) return false
      return excludedKeys.test(p.name.getText().replace(/["']/g, ''))
    }
    if (ts.isCallExpression(p) || ts.isFunctionLike(p) || ts.isStatement(p)) break
  }
  return false
}

function isCandidate(node, text) {
  if (!/[A-Za-z]/.test(text) || !text.trim() || protectedContext(node)) return false
  if (/^(?:Basic|Bearer) \{\d+\}$|^Keygen-(?:Environment|Version):|^P\{\d+\}D$/.test(text)) return false
  if (ts.isJsxText(node)) return true
  if (!displayMap(node) && /^(?:string|number|boolean|date|enum|json|raw)$/.test(text)) return false
  const p = node.parent
  if (ts.isCallExpression(p) && p.expression.getText() === 'titleHead') return true
  if (ts.isJsxAttribute(p)) return true
  if (ts.isPropertyAssignment(p)) {
    const key = p.name.getText().replace(/["']/g, '')
    if (displayKeys.test(key) && key !== 'name') return true
    if (key === 'name' && /^[A-Z]/.test(text) && !/^(?:SBOMScan|Keygen)/.test(text)) return true
    if (displayMap(node) && /^[A-Z][a-z]/.test(text) && !/[:/{}]/.test(text)) return true
  }
  if (ts.isBindingElement(p) && p.initializer === node && displayKeys.test(p.name.getText())) return true
  if (ts.isBinaryExpression(p) && p.right === node && [ts.SyntaxKind.BarBarToken, ts.SyntaxKind.AmpersandAmpersandToken, ts.SyntaxKind.QuestionQuestionToken].includes(p.operatorToken.kind)) {
    let ancestor = p.parent
    while (ancestor && !ts.isStatement(ancestor) && !ts.isFunctionLike(ancestor) && !ts.isCallExpression(ancestor)) {
      if (ts.isJsxExpression(ancestor)) return true
      ancestor = ancestor.parent
    }
  }
  // Human-readable sentences, including validation messages and ternary button labels.
  const displayText = text.replace(/\{\d+\}/g, 'value')
  if (/^[A-Z][a-z]/.test(displayText) && /[a-z][ ,.!?:]/.test(displayText) && !/[{}<>]|https?:|[\n\r]/.test(displayText)) return true
  if (ts.isConditionalExpression(p) || ts.isReturnStatement(p) || ts.isJsxExpression(p)) {
    return /^[A-Z][a-z]+(?:[ A-Za-z.!?…'-]*)$/.test(displayText)
  }
  return false
}

let changedFiles = 0
let changedStrings = 0
function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const file = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (!['demo', 'mock', 'locales'].includes(entry.name)) walk(file)
      continue
    }
    if (!/\.tsx?$/.test(file) || /routeTree\.gen|vite-env|\.d\.ts$/.test(file) || entry.name === 'license-i18n.tsx') continue
    const source = fs.readFileSync(file, 'utf8')
    const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
    const edits = []
    function visit(node) {
      if (ts.isJsxText(node) || ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isTemplateExpression(node)) {
        let text
        if (ts.isJsxText(node)) text = cleanJsx(node.text)
        else if (ts.isTemplateExpression(node)) text = node.head.text + node.templateSpans.map((span, i) => `{${i}}${span.literal.text}`).join('')
        else text = node.text
        if (isCandidate(node, text)) {
          found.set(text, [...(found.get(text) || []), path.relative(root, file)])
          if (!extract && Object.hasOwn(dictionary, text)) {
            let call = `licenseT(${JSON.stringify(text)}`
            if (ts.isTemplateExpression(node)) call += ', [' + node.templateSpans.map(s => s.expression.getText(sf)).join(', ') + ']'
            call += ')'
            if (ts.isJsxText(node) || ts.isJsxAttribute(node.parent)) call = '{' + call + '}'
            edits.push({ start: node.getStart(sf), end: node.end, text: call })
            return
          }
        }
      }
      ts.forEachChild(node, visit)
    }
    visit(sf)
    if (edits.length) {
      let updated = source
      for (const edit of edits.sort((a, b) => b.start - a.start)) updated = updated.slice(0, edit.start) + edit.text + updated.slice(edit.end)
      updated = 'import { t as licenseT } from "@/license-i18n"\n' + updated
      fs.writeFileSync(file, updated)
      changedFiles++
      changedStrings += edits.length
    }
  }
}
walk(root)
if (extract) {
  console.log(JSON.stringify(Object.fromEntries([...found].sort(([a], [b]) => a.localeCompare(b))), null, 2))
} else {
  const missing = [...found.keys()].filter(key => !Object.hasOwn(dictionary, key))
  console.log(`Localized ${changedStrings} strings in ${changedFiles} files; ${missing.length} untranslated candidates.`)
  fs.writeFileSync('/tmp/license-i18n-untranslated.json', JSON.stringify(missing, null, 2))
  if (missing.length) throw new Error(`Missing translations: ${missing.join(' | ')}`)
}
