/**
 * Check for duplicate type definitions between @/shared/api/types.ts
 * and @/generated/orval/models to prevent redundancy.
 *
 * Usage: ts-node scripts/check-duplicate-types.ts
 */

import fs from 'fs';
import path from 'path';

interface TypeInfo {
  name: string;
  file: string;
  line: number;
}

const projectRoot = path.resolve(__dirname, '..');
const webRoot = path.join(projectRoot, 'apps/web');
const srcRoot = path.join(webRoot, 'src');

/**
 * Extract exported type/interface names from a TypeScript file.
 */
function extractExportedTypes(filePath: string): TypeInfo[] {
  if (!fs.existsSync(filePath)) {
    return [];
  }

  const content = fs.readFileSync(filePath, 'utf-8');
  const lines = content.split('\n');
  const types: TypeInfo[] = [];

  // Match: export interface Foo {, export type Foo =, export enum Foo {, etc.
  const exportRegex = /export\s+(interface|type|enum)\s+(\w+)/;

  lines.forEach((line, index) => {
    const match = line.match(exportRegex);
    if (match) {
      const name = match[2];
      types.push({
        name,
        file: filePath,
        line: index + 1,
      });
    }
  });

  return types;
}

/**
 * Recursively get all .ts files from a directory.
 */
function getAllTypeScriptFiles(dir: string): string[] {
  const files: string[] = [];

  function traverse(currentDir: string) {
    try {
      const entries = fs.readdirSync(currentDir, { withFileTypes: true });
      for (const entry of entries) {
        const fullPath = path.join(currentDir, entry.name);
        if (entry.isDirectory()) {
          traverse(fullPath);
        } else if (entry.isFile() && entry.name.endsWith('.ts')) {
          files.push(fullPath);
        }
      }
    } catch (err) {
      // Skip directories we can't read
    }
  }

  traverse(dir);
  return files;
}

/**
 * Get relative path from web root for display.
 */
function getRelativePath(filePath: string): string {
  return path.relative(webRoot, filePath);
}

/**
 * Main check function.
 */
function checkDuplicateTypes() {
  const handwrittenTypesPath = path.join(srcRoot, 'shared/api/types.ts');
  const orvalModelsDir = path.join(srcRoot, 'generated/orval/models');

  console.log('📋 Checking for duplicate type definitions...\n');

  // Extract types from handwritten types file
  const handwrittenTypes = extractExportedTypes(handwrittenTypesPath);
  console.log(`Found ${handwrittenTypes.length} types in @/shared/api/types.ts`);

  // Get all orval model files
  const orvalFiles = getAllTypeScriptFiles(orvalModelsDir);
  console.log(`Scanning ${orvalFiles.length} files in @/generated/orval/models\n`);

  // Extract types from all orval models
  const orvalTypeMap = new Map<string, TypeInfo[]>();
  for (const file of orvalFiles) {
    const types = extractExportedTypes(file);
    for (const type of types) {
      if (!orvalTypeMap.has(type.name)) {
        orvalTypeMap.set(type.name, []);
      }
      orvalTypeMap.get(type.name)!.push(type);
    }
  }

  // Check for duplicates
  const duplicates: Array<{
    name: string;
    handwritten: TypeInfo;
    orval: TypeInfo[];
  }> = [];

  for (const handWritten of handwrittenTypes) {
    const orvalMatches = orvalTypeMap.get(handWritten.name);
    if (orvalMatches && orvalMatches.length > 0) {
      duplicates.push({
        name: handWritten.name,
        handwritten: handWritten,
        orval: orvalMatches,
      });
    }
  }

  if (duplicates.length === 0) {
    console.log('✅ No duplicate types found. All handwritten types are unique.\n');
    return 0;
  }

  console.log(`❌ Found ${duplicates.length} duplicate type(s):\n`);

  for (const dup of duplicates) {
    console.log(`  📌 ${dup.name}`);
    console.log(
      `     Handwritten: ${getRelativePath(dup.handwritten.file)}:${dup.handwritten.line}`
    );
    for (const orvalType of dup.orval) {
      console.log(
        `     Generated:   ${getRelativePath(orvalType.file)}:${orvalType.line}`
      );
    }
    console.log();
  }

  console.log(
    '⚠️  These types should be removed from @/shared/api/types.ts'
  );
  console.log('   and imported directly from @/generated/orval/models instead.\n');

  return 1;
}

// Run
const exitCode = checkDuplicateTypes();
process.exit(exitCode);
