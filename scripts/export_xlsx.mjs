#!/usr/bin/env node
/** Optional XLSX author using the public @oai/artifact-tool API.
 * Base report export stays independent of this script and of Node.
 * Usage: node export_xlsx.mjs --input workbook_data.json --output report.xlsx
 *   --modules <loader-node_modules> [--preview-dir <directory>]
 */
import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

function options(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    if (!["--input", "--output", "--modules", "--preview-dir"].includes(key) || !argv[index + 1]) {
      throw new Error("Usage: export_xlsx.mjs --input workbook_data.json --output report.xlsx [--modules node_modules] [--preview-dir directory]");
    }
    result[key.slice(2)] = argv[++index];
  }
  if (!result.input || !result.output) throw new Error("--input and --output are required");
  return result;
}

function literal(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error("Non-finite numbers cannot be exported");
    return value;
  }
  if (typeof value === "boolean") return value;
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (text.length > 32767) throw new Error("XLSX cell exceeds 32767 characters; use the complete report.json/HTML or split the source field explicitly. No truncation was performed.");
  return /^[\uFEFF\s]*[=+@-]/u.test(text) ? "'" + text : text;
}

function columnName(index) {
  let answer = "";
  for (let current = index + 1; current > 0; current = Math.floor((current - 1) / 26)) {
    answer = String.fromCharCode(65 + (current - 1) % 26) + answer;
  }
  return answer;
}

function wrappedLines(value, width) {
  return String(value ?? "").split(/\r?\n/).reduce((total, line) => {
    const units = [...line].reduce((count, character) => count + (character.codePointAt(0) > 255 ? 2 : 1), 0);
    return total + Math.max(1, Math.ceil(units / (width - 2)));
  }, 0);
}

async function main() {
  const args = options(process.argv.slice(2));
  let artifact;
  const modules = args.modules || process.env.FAULTAUDIT_NODE_MODULES;
  try {
    if (modules) {
      const resolver = createRequire(path.resolve(modules, "..", "__faultaudit_resolver__.cjs"));
      artifact = await import(pathToFileURL(resolver.resolve("@oai/artifact-tool")).href);
    } else {
      artifact = await import("@oai/artifact-tool");
    }
  } catch (error) {
    throw new Error("Optional XLSX runtime unavailable. Set --modules or FAULTAUDIT_NODE_MODULES to the loader's node_modules. JSON, HTML and TSV remain available. " + error.message);
  }
  const { Workbook, SpreadsheetFile } = artifact;
  const input = JSON.parse(await fs.readFile(path.resolve(args.input), "utf8"));
  if (input.schema_version !== "1.0" || !Array.isArray(input.sheets) || input.sheets.length === 0) {
    throw new Error("Expected workbook_data schema_version 1.0 with non-empty sheets");
  }
  const destination = path.resolve(args.output);
  const previewDir = path.resolve(args["preview-dir"] || destination.replace(/\.xlsx$/i, "") + "_previews");
  await fs.mkdir(path.dirname(destination), { recursive: true });
  await fs.mkdir(previewDir, { recursive: true });
  const workbook = Workbook.create();
  const usedNames = new Set();
  const created = [];
  for (let index = 0; index < input.sheets.length; index += 1) {
    const table = input.sheets[index];
    if (!Array.isArray(table.columns) || table.columns.length === 0 || !Array.isArray(table.rows)) {
      throw new Error(`Invalid table shape at sheet ${index}`);
    }
    if (table.columns.length > 16384 || table.rows.length >= 1048576) throw new Error("XLSX worksheet dimensions exceeded");
    let name = String(table.name || `Sheet ${index + 1}`).replace(/[\\/?*\[\]:]/g, " ").slice(0, 31);
    while (usedNames.has(name)) name = name.slice(0, 26) + ` ${index + 1}`;
    usedNames.add(name);
    const matrix = [table.columns.map(literal), ...table.rows.map((row, rowIndex) => {
      if (!Array.isArray(row) || row.length !== table.columns.length) throw new Error(`Row width mismatch at ${name}:${rowIndex + 2}`);
      return row.map(literal);
    })];
    const sheet = workbook.worksheets.add(name);
    sheet.showGridLines = false;
    sheet.tabColor = index === 0 ? "#223F62" : "#CCD5E0";
    const endColumn = columnName(table.columns.length - 1);
    const endRow = matrix.length;
    const range = sheet.getRange(`A1:${endColumn}${endRow}`);
    range.values = matrix;
    range.format.font = { name: "Arial", size: 10, color: "#172B4D" };
    range.format.verticalAlignment = "center";
    range.format.columnWidth = 24;
    range.format.rowHeight = 24;
    range.format.wrapText = true;
    sheet.getRange(`A1:${endColumn}1`).format = {
      fill: "#223F62", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
      rowHeight: 36, wrapText: true, horizontalAlignment: "center", verticalAlignment: "center",
    };
    const columnWidths = table.columns.map(() => 24);
    for (let column = 0; column < table.columns.length; column += 1) {
      const label = String(table.columns[column]);
      if (label === "变量及依据") {
        columnWidths[column] = 160;
      } else if (label === "完整条件核对") {
        columnWidths[column] = 128;
      } else if (label === "完整执行规程") {
        columnWidths[column] = 104;
      } else if (/^(参考计算|目标路径|检查项|执行步骤|能力要求)$/.test(label)) {
        columnWidths[column] = 72;
      } else if (/谓词检查|条件核对|机理及未知边界/.test(label)) {
        columnWidths[column] = 104;
      } else if (/^(原文定位|精确引文及单元格)$/.test(label)) {
        columnWidths[column] = 240;
      } else if (/引文|原文.*位置|原文定位|单元格定位/.test(label)) {
        columnWidths[column] = 120;
      } else if (label === "未知项") {
        columnWidths[column] = 96;
      } else if (label === "来源文件") {
        columnWidths[column] = 72;
      } else if (/描述|根因|判断|定义|缺口|理由|说明|原因|建议|事实原义|机理|边界|未确定项|未知项|reason|text|content|facts|evidence|issues|raw/.test(label)) {
        columnWidths[column] = 48;
      }
      sheet.getRange(`${columnName(column)}1:${columnName(column)}${endRow}`).format.columnWidth = columnWidths[column];
    }
    if (matrix.length > 1) {
      sheet.getRange(`A2:${endColumn}${endRow}`).format.verticalAlignment = "top";
      sheet.getRange(`A2:${endColumn}${endRow}`).format.autofitRows();
      // Whole-range autofit can under-size newline-rich predicate cells and
      // over-size unrelated rows. Size each persisted row from all its cells.
      for (let row = 1; row < matrix.length; row += 1) {
        const lines = Math.max(...matrix[row].map((value, column) => wrappedLines(value, columnWidths[column])));
        sheet.getRange(`A${row + 1}:${endColumn}${row + 1}`).format.rowHeight = Math.max(24, lines * 13 + 8);
      }
      const excelTable = sheet.tables.add(`A1:${endColumn}${endRow}`, true, `AuditTable${index + 1}`);
      excelTable.showFilterButton = true;
      excelTable.showBandedColumns = false;
    }
    sheet.freezePanes.freezeRows(1);
    sheet.freezePanes.freezeColumns(index === 0 ? 3 : 1);
    created.push({ sheet, name, endColumn, endRow, columns: table.columns.length, count: table.rows.length });
  }
  workbook.recalculate();
  const checks = [];
  for (let index = 0; index < created.length; index += 1) {
    const entry = created[index];
    const range = `A1:${columnName(Math.min(entry.columns, 6) - 1)}${Math.min(entry.endRow, 7)}`;
    const inspection = await workbook.inspect({ kind: "table", range: `'${entry.name.replaceAll("'", "''")}'!${range}`, include: "values,formulas", tableMaxRows: 7, tableMaxCols: 6, maxChars: 2500 });
    checks.push({ sheet: entry.name, rows: entry.count, inspection: inspection.ndjson });
    const preview = await workbook.render({ sheetName: entry.name, range, scale: 1.4, format: "png" });
    await fs.writeFile(path.join(previewDir, `${String(index + 1).padStart(2, "0")}.png`), new Uint8Array(await preview.arrayBuffer()));
  }
  const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, maxChars: 3500 });
  await fs.writeFile(path.join(previewDir, "inspection.json"), JSON.stringify({ checks, formulaErrorScan: errors.ndjson }, null, 2), "utf8");
  const xlsx = await SpreadsheetFile.exportXlsx(workbook);
  await xlsx.save(destination);
  if ((await fs.stat(destination)).size === 0) throw new Error("XLSX export produced an empty file");
  console.log(JSON.stringify({ xlsx: destination, preview_dir: previewDir, sheets: created.map(({ name, count }) => ({ name, rows: count })) }));
  // All authoring, inspections and saves are awaited. End optional worker
  // lifetimes only after the persisted workbook has been checked non-empty.
  process.exit(0);
}

main().catch((error) => {
  console.error(JSON.stringify({ error: error.message, xlsx_created: false }));
  process.exit(1);
});
