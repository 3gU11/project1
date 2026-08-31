import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workbookPath = "D:/CURSORpj/V8BetaV1.1/2026.7.2\u5408\u540c_\u672a\u627e\u5230.xlsx";
const tempPath = "D:/CURSORpj/V8BetaV1.1/2026.7.2\u5408\u540c_\u672a\u627e\u5230.fixed.xlsx";
const previewPath = "D:/CURSORpj/V8BetaV1.1/missing_contracts_date_fixed_preview.png";

const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItem("Sheet1");

sheet.getRange("A1:A95").setNumberFormat('m"\u6708"d"\u65e5"');

const preview = await workbook.render({
  sheetName: "Sheet1",
  range: "A1:I25",
  scale: 1,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(tempPath);
await fs.copyFile(tempPath, workbookPath);
await fs.rm(tempPath);

const check = await workbook.inspect({
  kind: "table",
  sheetId: "Sheet1",
  range: "A1:I5",
  include: "values,formulas",
  tableMaxRows: 5,
  tableMaxCols: 9,
  maxChars: 3000,
});
console.log(check.ndjson);
console.log(`saved=${workbookPath}`);
console.log(`preview=${previewPath}`);
