import * as fs from 'fs'
import * as path from 'path'

interface E2ERow {
  old_path: string
  old_test_title: string
  new_path: string
  new_test_title: string
  mode: string
  status: string
  notes: string
}

interface VitestRow {
  old_path: string
  old_describe: string
  old_it_titles: string
  new_path: string
  status: string
  notes: string
}

function webRoot(): string {
  return process.cwd()
}

function resolveOld(p: string): string {
  return path.resolve(webRoot(), p)
}

function resolveNew(p: string): string {
  return path.resolve(webRoot(), 'tests', p)
}

function fileExists(p: string): boolean {
  try {
    fs.accessSync(p, fs.constants.R_OK)
    return true
  } catch {
    return false
  }
}

interface TableMatch {
  bodyLines: string[]
}

function findTable(md: string, firstHeader: string): TableMatch | null {
  const lines = md.split('\n')
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim()
    if (!line.startsWith('|')) continue
    const cols = parseRow(line)
    if (cols.length > 0 && cols[0].trim() === firstHeader) {
      const bodyLines: string[] = []
      for (let j = i + 2; j < lines.length; j++) {
        const bodyLine = lines[j].trim()
        if (!bodyLine.startsWith('|')) break
        if (bodyLine.startsWith('|--')) continue
        bodyLines.push(bodyLine)
      }
      return { bodyLines }
    }
  }
  return null
}

function parseRow(line: string): string[] {
  let trimmed = line.trim()
  if (trimmed.startsWith('|')) trimmed = trimmed.slice(1)
  if (trimmed.endsWith('|')) trimmed = trimmed.slice(0, -1)
  return trimmed.split('|').map((s) => s.trim())
}

function parseE2ETable(md: string): E2ERow[] {
  const match = findTable(md, 'old_path')
  if (!match) {
    console.error('ERROR: Could not find Playwright E2E table in migration-map.md')
    process.exit(2)
  }
  return match.bodyLines.map((line) => {
    const cols = parseRow(line)
    return {
      old_path: cols[0] ?? '',
      old_test_title: cols[1] ?? '',
      new_path: cols[2] ?? '',
      new_test_title: cols[3] ?? '',
      mode: cols[4] ?? '',
      status: cols[5] ?? '',
      notes: cols[6] ?? '',
    }
  }).filter((r) => r.old_path)
}

function parseVitestTable(md: string): VitestRow[] {
  const sections = md.split(/^## /m)
  let vitestSection = ''
  for (const sec of sections) {
    if (sec.startsWith('Vitest Unit Tests')) {
      vitestSection = sec
      break
    }
  }
  if (!vitestSection) {
    console.error('ERROR: Could not find Vitest Unit Tests section in migration-map.md')
    process.exit(2)
  }

  const match = findTable(vitestSection, 'old_path')
  if (!match) {
    console.error('ERROR: Could not find Vitest table in migration-map.md')
    process.exit(2)
  }

  return match.bodyLines.map((line) => {
    const cols = parseRow(line)
    return {
      old_path: cols[0] ?? '',
      old_describe: cols[1] ?? '',
      old_it_titles: cols[2] ?? '',
      new_path: cols[3] ?? '',
      status: cols[4] ?? '',
      notes: cols[5] ?? '',
    }
  }).filter((r) => r.old_path)
}

interface ValidationIssue {
  level: 'error' | 'warn'
  row: number
  type: 'e2e' | 'vitest'
  message: string
}

function validate(rows: E2ERow[], vitestRows: VitestRow[]): ValidationIssue[] {
  const issues: ValidationIssue[] = []

  let rowNum = 0
  for (const row of rows) {
    rowNum++
    const oldFullPath = resolveOld(row.old_path)

    if (row.status === 'pending' && !fileExists(oldFullPath)) {
      issues.push({
        level: 'warn',
        row: rowNum,
        type: 'e2e',
        message: `old_path "${row.old_path}" no longer exists on disk`,
      })
    }

    if (row.status === 'migrated') {
      const newPath = row.new_path
      if (newPath && newPath !== '-') {
        const newFull = resolveNew(newPath)
        if (!fileExists(newFull)) {
          issues.push({
            level: 'error',
            row: rowNum,
            type: 'e2e',
            message: `migrated new_path "${newPath}" does not exist on disk`,
          })
        }
      } else {
        issues.push({
          level: 'error',
          row: rowNum,
          type: 'e2e',
          message: 'migrated row has no new_path',
        })
      }
    }

    if (row.status === 'dropped' && (!row.notes || row.notes.trim() === '')) {
      issues.push({
        level: 'error',
        row: rowNum,
        type: 'e2e',
        message: 'dropped row must have non-empty notes',
      })
    }
  }

  rowNum = 0
  for (const row of vitestRows) {
    rowNum++
    const oldFullPath = resolveOld(row.old_path)

    if (row.status === 'pending' && !fileExists(oldFullPath)) {
      issues.push({
        level: 'warn',
        row: rowNum,
        type: 'vitest',
        message: `old_path "${row.old_path}" no longer exists on disk`,
      })
    }

    if (row.status === 'migrated') {
      const newPath = row.new_path
      if (newPath && newPath !== '-') {
        const newFull = resolveNew(newPath)
        if (!fileExists(newFull)) {
          issues.push({
            level: 'error',
            row: rowNum,
            type: 'vitest',
            message: `migrated new_path "${newPath}" does not exist on disk`,
          })
        }
      } else {
        issues.push({
          level: 'error',
          row: rowNum,
          type: 'vitest',
          message: 'migrated row has no new_path',
        })
      }
    }

    if (row.status === 'dropped' && (!row.notes || row.notes.trim() === '')) {
      issues.push({
        level: 'error',
        row: rowNum,
        type: 'vitest',
        message: 'dropped row must have non-empty notes',
      })
    }
  }

  return issues
}

function countBy(rows: { status: string }[]): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const r of rows) {
    counts[r.status] = (counts[r.status] || 0) + 1
  }
  return counts
}

function main() {
  const args = process.argv.slice(2)
  const dryRun = args.includes('--dry-run')
  const strict = args.includes('--strict')

  const mapPath = path.resolve(webRoot(), 'tests/migration-map.md')
  if (!fileExists(mapPath)) {
    console.error(`ERROR: migration-map.md not found at ${mapPath}`)
    process.exit(2)
  }

  const md = fs.readFileSync(mapPath, 'utf-8')
  const e2eRows = parseE2ETable(md)
  const vitestRows = parseVitestTable(md)

  const e2eCounts = countBy(e2eRows)
  const vitestCounts = countBy(vitestRows)
  const allE2E = e2eRows.length
  const allVitest = vitestRows.length

  const issues = validate(e2eRows, vitestRows)
  const errors = issues.filter((i) => i.level === 'error')

  if (dryRun) {
    console.log('=== Playwright E2E Tests ===')
    console.log(`  pending=${e2eCounts['pending'] || 0}, migrated=${e2eCounts['migrated'] || 0}, dropped=${e2eCounts['dropped'] || 0}, total=${allE2E}`)
    console.log('=== Vitest Unit Tests ===')
    console.log(`  pending=${vitestCounts['pending'] || 0}, migrated=${vitestCounts['migrated'] || 0}, dropped=${vitestCounts['dropped'] || 0}, total=${allVitest}`)
    const totalPending = (e2eCounts['pending'] || 0) + (vitestCounts['pending'] || 0)
    const totalMigrated = (e2eCounts['migrated'] || 0) + (vitestCounts['migrated'] || 0)
    const totalDropped = (e2eCounts['dropped'] || 0) + (vitestCounts['dropped'] || 0)
    console.log(`=== Overall: pending=${totalPending}, migrated=${totalMigrated}, dropped=${totalDropped}, total=${allE2E + allVitest}`)
  }

  if (issues.length > 0) {
    console.log('')
    console.log('=== Validation Issues ===')
    for (const issue of issues) {
      const prefix = issue.level === 'error' ? 'ERROR' : 'WARN'
      console.log(`  [${prefix}] [${issue.type} row ${issue.row}] ${issue.message}`)
    }
  }

  let exitCode = 0

  if (strict) {
    const pendingE2E = e2eRows.filter((r) => r.status === 'pending')
    const pendingVitest = vitestRows.filter((r) => r.status === 'pending')
    const totalPending = pendingE2E.length + pendingVitest.length

    if (totalPending > 0) {
      console.log('')
      console.log(`=== STRICT MODE: ${totalPending} pending rows found ===`)
      console.log('')
      console.log('Pending Playwright rows:')
      for (const r of pendingE2E) {
        console.log(`  [${r.mode}] ${r.old_path}: "${r.old_test_title}"`)
      }
      console.log('')
      console.log('Pending Vitest rows:')
      for (const r of pendingVitest) {
        console.log(`  ${r.old_path}: ${r.old_describe} -> [${r.old_it_titles}]`)
      }
      exitCode = 1
    }
  }

  if (errors.length > 0) {
    exitCode = Math.max(exitCode, 1)
  }

  process.exit(exitCode)
}

main()
